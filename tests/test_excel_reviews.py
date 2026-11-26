from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from smishing_backend.data.repositories.poisoning import flag_content
from smishing_backend.data.review_excel import COLUMNS, MAX_BODY_BYTES, MAX_FILE_BYTES, MAX_ROWS, SHEET
from smishing_backend.data.schema import contributions, reviews
from test_management import client as client
from test_management import ADMIN, MOBILE, REVIEWER, contribute

EXPORT = "/api/v1/admin/exports/contributions.xlsx"
IMPORT = "/api/v1/admin/exports/reviews.xlsx"


def file(book):
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def upload(client, content, name="sintetico.xlsx", headers=ADMIN):
    return client.post(IMPORT, files={"file": (name, content)}, headers=headers)


def test_workbook_round_trip_synthetic_text_conflicts_and_idempotency(client, pg):
    values = {contribute(client, f"{prefix} Aviso sintético {i} <URL>"): f"{prefix} Aviso sintético {i} <URL>" for i, prefix in enumerate("=+-@")}
    flagged = next(iter(values))
    with pg.begin() as connection:
        flag_content(connection, UUID(flagged), "label_conflict")
    response = client.get(EXPORT, params={"status": "pending", "source": "device", "model_version": "1.0.0"}, headers=ADMIN)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].endswith('.xlsx"')
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == [SHEET, "Instrucciones"]
    sheet = book[SHEET]
    for row in sheet.iter_rows(min_row=2, max_col=12):
        identity = row[0].value
        assert row[3].value == values[identity] and row[3].data_type == "s"
        assert row[6].value == "1.0.0"
        row[8].value, row[9].value, row[10].value = "accepted", "smishing", "quality_checked"
        row[11].value = identity == flagged
    original = list(sheet.iter_rows(min_row=2, max_row=2, values_only=True))[0]
    sheet.append((str(uuid4()), *original[1:]))
    sheet.append((*original[:4], "a" * 64, *original[5:]))
    sheet.append((*original[:6], "9.9.9", *original[7:]))
    sheet.append((*original[:8], "=SYNTHETIC_FORMULA_MARKER", *original[9:]))
    body = file(book)
    response = upload(client, body)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert [row["status"] for row in response.json()["rows"]] == ["applied"] * 4 + ["rejected"] * 4
    assert all(value not in response.text for value in (*values.values(), "SYNTHETIC_FORMULA_MARKER"))
    repeated = upload(client, body)
    assert [row["status"] for row in repeated.json()["rows"]] == ["skipped"] * 4 + ["rejected"] * 4
    with pg.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(reviews)) == 4
        assert set(connection.scalars(select(reviews.c.reviewer_id))) == {"operator"}
        assert set(connection.scalars(select(contributions.c.text))) == set(values.values())
    assert client.get(EXPORT, params={"status": "pending"}, headers=ADMIN).status_code == 200


def test_file_and_row_bounds_and_wrong_credentials(client):
    for credentials in ({}, MOBILE, REVIEWER):
        assert upload(client, b"invalid", headers=credentials).status_code == 401
        assert client.get(EXPORT, headers=credentials).status_code == 401
    assert upload(client, b"private-invalid-marker").status_code == 422
    assert "private-invalid-marker" not in upload(client, b"private-invalid-marker").text
    assert upload(client, b"x"*(MAX_FILE_BYTES+1)).status_code == 413
    assert upload(client, b"x"*(MAX_BODY_BYTES+1)).status_code == 413
    assert upload(client, b"invalid", "sintetico.xlsm").status_code == 422
    book = Workbook()
    book.active.title = SHEET
    book.active.append(COLUMNS)
    book.active.cell(MAX_ROWS+2, 1, "out of bounds")
    assert upload(client, file(book)).status_code == 413
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/vbaProject.bin", "synthetic")
    assert upload(client, output.getvalue()).status_code == 422
    assert client.get(EXPORT, params={"limit": MAX_ROWS+1}, headers=ADMIN).status_code == 422
