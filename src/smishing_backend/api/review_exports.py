"""Import and export the research review template from the main Swagger."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import Field, ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from smishing_backend.api.management import FilterQuery, ManagementRoute
from smishing_backend.data.review_excel import MAX_BODY_BYTES, MAX_FILE_BYTES, MAX_ROWS, decode_workbook, encode_workbook, row_identity
from smishing_backend.domain.administration import ManagementError
from smishing_backend.domain.quarantine import InvalidTransition
from smishing_backend.domain.review import ReviewAlreadyRecorded, ReviewExpectation
from smishing_backend.review_contract import ReviewInput

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
router = APIRouter(prefix="/exports", tags=["Excel de revisión"], route_class=ManagementRoute)


class ExcelQuery(FilterQuery):
    limit: int = Field(default=MAX_ROWS, ge=1, le=MAX_ROWS)
    offset: int = Field(default=0, ge=0, le=1_000_000)


@router.get("/contributions.xlsx", response_class=Response, responses={200: {"content": {XLSX: {"schema": {"type": "string", "format": "binary"}}}}})
def download(request: Request, query: Annotated[ExcelQuery, Query()]):
    rows = request.app.state.management.list_contributions(query.filters(), query.limit, query.offset)
    workbook = encode_workbook(rows)
    if len(workbook) > MAX_FILE_BYTES:
        raise ManagementError(413)
    return Response(workbook, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="aportes-revision.xlsx"'})


class OversizeMultipart(MultiPartException):
    pass


class MemoryMultipart(MultiPartParser):
    # The entire request is smaller than this. No upload spools to disk.
    spool_max_size = MAX_BODY_BYTES + 1


async def read_upload(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise ManagementError(422)

    async def bounded_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise OversizeMultipart("Request too large")
            yield chunk

    try:
        form = await MemoryMultipart(request.headers, bounded_stream(), max_files=1, max_fields=0).parse()
    except OversizeMultipart:
        raise ManagementError(413) from None
    except (MultiPartException, ValueError):
        raise ManagementError(422) from None
    try:
        upload = form.get("file")
        if len(form) != 1 or not isinstance(upload, UploadFile) or not (upload.filename or "").lower().endswith(".xlsx"):
            raise ManagementError(422)
        content = await upload.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ManagementError(413)
        return content
    finally:
        await form.close()


def import_rows(repository, actor: str, content: bytes) -> list[dict]:
    results = []
    for row, values in decode_workbook(content):
        result = {"row": row, "status": "rejected", "reason": "invalid_row"}
        if values is not None:
            try:
                identity, digest, version = row_identity(values)
                if all(values[key] in (None, "") for key in ("decision", "label", "reason", "acknowledge_flags")):
                    results.append({"row": row, "status": "skipped", "reason": "no_decision"})
                    continue
                acknowledge = values["acknowledge_flags"]
                if isinstance(acknowledge, str) and acknowledge.lower() == "true":
                    acknowledge = True
                decision = ReviewInput.model_validate({
                    "decision": values["decision"], "label": values["label"],
                    "reason": values["reason"], "acknowledge_flags": False if acknowledge is None else acknowledge,
                })
                repository.decide(identity, actor, decision.to_decision(), expectation=ReviewExpectation(digest, version))
                result.update(status="applied", reason="recorded")
            except ReviewAlreadyRecorded:
                result.update(status="skipped", reason="already_reviewed")
            except InvalidTransition:
                result.update(reason="review_conflict")
            except (IntegrityError, ManagementError):
                result.update(reason="row_not_applicable")
            except (ValidationError, ValueError):
                pass
        results.append(result)
    return results


@router.post(
    "/reviews.xlsx",
    openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}},
)
async def upload(request: Request):
    content = await read_upload(request)
    results = await run_in_threadpool(import_rows, request.app.state.reviews, request.state.administrative_actor, content)
    return {"rows": results}
