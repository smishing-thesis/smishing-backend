"""Authenticated, reproducible download for the model pipeline."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from smishing_backend.api.management import ManagementRoute
from smishing_backend.domain.administration import ManagementError
from smishing_backend.domain.corpus_export import InvalidCorpusExport, render_corpus

MAX_CORPUS_ROWS = 500
router = APIRouter(prefix="/corpus", tags=["Corpus final"], route_class=ManagementRoute)


@router.get(
    "/accepted.csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}
        }
    },
)
def download(request: Request):
    rows, excluded = request.app.state.corpus.reviewed_for_training(MAX_CORPUS_ROWS)
    if len(rows) > MAX_CORPUS_ROWS:
        raise ManagementError(413)
    try:
        artifact = render_corpus(rows)
    except InvalidCorpusExport:
        raise ManagementError(503) from None
    date = datetime.now(UTC).date().isoformat()
    return Response(
        artifact.csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="corpus-{date}-{artifact.version}.csv"',
            "X-Corpus-Date": date,
            "X-Corpus-Version": artifact.version,
            "X-Corpus-Rows": str(artifact.count),
            "X-Corpus-Excluded": str(excluded),
        },
    )
