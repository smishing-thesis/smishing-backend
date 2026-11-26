"""Bounded Excel interchange. Uploaded cells never become executable input."""

from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from smishing_backend.domain.administration import ManagementError

MAX_ROWS = 500
MAX_FILE_BYTES = 512 * 1024
MAX_BODY_BYTES = MAX_FILE_BYTES + 16 * 1024
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
COLUMNS = (
    "id",
    "received_at",
    "status",
    "text",
    "content_hash",
    "automatic_label",
    "model_version",
    "risk_signals",
    "decision",
    "label",
    "reason",
    "acknowledge_flags",
)
SHEET = "Aportes"


def encode_workbook(rows: list[dict]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    sheet.append(COLUMNS)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:L{len(rows) + 1}"
    sheet.column_dimensions["D"].width = 75
    for row_index, row in enumerate(rows, 2):
        values = (
            str(row["id"]),
            row["received_at"].isoformat(),
            row["status"],
            row["text"],
            row["content_hash"],
            row["automatic_label"],
            row["model_version"],
            ", ".join(row["risk_signals"]),
        )
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row=row_index, column=column, value=value)
            # Setting the type explicitly preserves all leading characters verbatim.
            cell.data_type = "s"
    instructions = book.create_sheet("Instrucciones")
    for line in (
        "Completa solo las últimas cuatro columnas. Conserva encabezados, UUID, huella y versión.",
        "decision: accepted o rejected. label: safe o smishing.",
        "reason: quality_checked, invalid_content u out_of_scope.",
        "Si revisaste las alertas, escribe true en acknowledge_flags. De lo contrario déjalo vacío.",
        "Las filas sin decisión no se aplican. Una revisión existente es terminal.",
    ):
        instructions.append([line])
    instructions.column_dimensions["A"].width = 100
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def _check_archive(source: BytesIO) -> None:
    with ZipFile(source) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        if (
            len(entries) > 128
            or len(names) != len(entries)
            or sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES
            or any(entry.flag_bits & 1 for entry in entries)
            or any(
                "vbaproject" in name.lower()
                or name.startswith(("xl/externalLinks/", "xl/embeddings/"))
                for name in names
            )
        ):
            raise ValueError("Unsupported archive")


def decode_workbook(content: bytes) -> list[tuple[int, dict | None]]:
    """Validate the file before performing any changes; invalid rows are isolated."""
    if not content or len(content) > MAX_FILE_BYTES:
        raise ManagementError(413 if content else 422)
    source = BytesIO(content)
    try:
        _check_archive(source)
        book = load_workbook(source, read_only=True, data_only=False, keep_links=False)
        try:
            sheet = book[SHEET]
            sheet.reset_dimensions()
            rows = sheet.iter_rows(max_col=len(COLUMNS))
            header = next(rows)
            if tuple(cell.value for cell in header) != COLUMNS:
                raise ValueError("Invalid template")
            output: list[tuple[int, dict | None]] = []
            for number, cells in enumerate(rows, 2):
                if number > MAX_ROWS + 1:
                    raise ManagementError(413)
                values = dict(zip(COLUMNS, (cell.value for cell in cells), strict=True))
                if not any(value is not None for value in values.values()):
                    continue
                if any(cell.data_type == "f" for cell in cells):
                    output.append((number, None))
                else:
                    output.append((number, values))
            return output
        finally:
            book.close()
    except ManagementError:
        raise
    except Exception:
        # Malformed OOXML can raise errors from multiple XML/ZIP layers.
        raise ManagementError(422) from None


def row_identity(values: dict):
    identity = UUID(values["id"]) if isinstance(values["id"], str) else None
    digest, version = values["content_hash"], values["model_version"]
    if (
        identity is None
        or not isinstance(digest, str)
        or len(digest) != 64
        or not isinstance(version, str)
        or not 1 <= len(version) <= 20
    ):
        raise ValueError("Invalid row identity")
    return identity, digest, version
