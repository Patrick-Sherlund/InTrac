import io
import json
import re
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from app.report import collect_report, render_report
from app.storage import connect
from test_logs import password_hash, photo_bytes, setup, sign_in


CATEGORIES = ["Handgun", "Rifle", "Shotgun", "Machine gun", "Ammunition", "Other & custom"]
GENERATED_AT = datetime(2026, 9, 18, 12, 30, tzinfo=timezone.utc)


def insert_log(connection, user_id, occurred_at, status="OPEN"):
    return connection.execute(
        "INSERT INTO operation_logs (user_id, operation_name, occurred_at, created_at, operator_name, "
        "location_name, status, reviewed_at, reviewed_by_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, "PRIVATE-OPERATION-NAME", occurred_at, occurred_at, "Observed person", "Private location", status,
         occurred_at if status == "REVIEWED" else None, "Avery Jones" if status == "REVIEWED" else None),
    ).lastrowid


def insert_weapon(connection, log_id, item_type, quantity, serial="", model="", photo=None, serials=None):
    connection.execute(
        "INSERT INTO weapons (log_id, item_type, quantity, serial_number, name_model, created_at, photo, "
        "photo_content_type, serial_numbers) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (log_id, item_type, quantity, serial, model, "2026-09-17T12:00:00Z", photo,
         "image/png" if photo else None, json.dumps(serials) if serials is not None else None),
    )


def collected(path, log_ids, username="verifier"):
    with connect(path) as connection:
        user_id = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]
        return collect_report(connection, user_id, log_ids)


def zero_report():
    return {
        "operation_count": 0, "verified_count": 0, "open_count": 0, "record_count": 0,
        "total_quantity": 0, "serial_count": 0, "photo_count": 0, "model_count": 0,
        "period_start": None, "period_end": None,
        "categories": [
            {"name": name, "records": 0, "quantity": 0, "serial_count": 0, "missing_serial_count": 0}
            for name in CATEGORIES
        ],
    }


def summary_page(content):
    assert content.startswith(b"%PDF-")
    document = PdfReader(io.BytesIO(content))
    for page in document.pages:
        assert float(page.mediabox.width) == 612
        assert float(page.mediabox.height) == 792
    assert not list(document.pages[0].images)
    return document.pages[0].extract_text()


def single_letter_page(content):
    assert len(PdfReader(io.BytesIO(content)).pages) == 1
    return summary_page(content)


@pytest.fixture
def populated(setup):
    client, path = setup
    photo = photo_bytes()
    with connect(path) as connection:
        users = {row["username"]: row["id"] for row in connection.execute("SELECT id, username FROM users")}
        first = insert_log(connection, users["verifier"], "2026-09-01T00:00:00Z")
        reviewed = insert_log(connection, users["verifier"], "2026-09-05T00:00:00Z", "REVIEWED")
        opened = insert_log(connection, users["verifier"], "2026-09-10T00:00:00Z")
        last = insert_log(connection, users["verifier"], "2026-09-17T23:59:00Z", "REVIEWED")
        for item_type, quantity, serial, model, image in [
            ("Pistol", 2, "SERIAL-1", "P9", photo),
            ("  reVOLVer ", 1, " \t ", "P9", None),
            (" hAnDgUn ", 4, "SERIAL-3", "", photo),
            ("Rifle", 3, "R1", "R model", None),
            ("Shotgun", 1, "", "  ", None),
            (" SUBMACHINE   gun ", 5, "S1", "SM", photo),
            ("machine gun", 2, "", "", None),
        ]:
            insert_weapon(connection, reviewed, item_type, quantity, serial, model, image)
        for item_type, quantity, serial, model in [
            (" AMMUNITION ", 100000, "", "9 mm"),
            ("Ammunition", 50, "LOT-5", " \t "),
            ("PRIVATE-CUSTOM-TYPE-π", 7, "  C1 ", "Tool"),
            ("   ", 1, "", ""),
        ]:
            insert_weapon(connection, opened, item_type, quantity, serial, model)
        other = insert_log(connection, users["other"], "2030-01-01T00:00:00Z", "REVIEWED")
        insert_weapon(connection, other, "Rifle", 99999, "OTHER-SERIAL", "Other model", photo)
    return client, path, [first, reviewed, opened, last], other


def test_selected_empty_operation_has_zero_weapon_totals_and_fixed_categories(populated):
    client, path, own_ids, _ = populated
    data = collected(path, [own_ids[0]])
    expected = zero_report()
    expected.update(operation_count=1, open_count=1, period_start="2026-09-01T00:00:00Z",
                    period_end="2026-09-01T00:00:00Z")
    assert data == expected
    response = client.post("/api/logs/report.pdf", json={"log_ids": [own_ids[0]]})
    assert response.status_code == 200
    single_letter_page(response.content)


def test_zero_data_renders_one_letter_page():
    text = single_letter_page(render_report(zero_report(), "verifier", GENERATED_AT))
    assert "INTRAC" in text.upper()
    assert "verifier" in text


def test_report_aggregates_owned_operations_with_legacy_serials_and_unit_based_coverage(populated):
    _, path, own_ids, _ = populated
    data = collected(path, own_ids)
    assert data["operation_count"] == 4
    assert data["verified_count"] == 2
    assert data["open_count"] == 2
    assert data["period_start"] == "2026-09-01T00:00:00Z"
    assert data["period_end"] == "2026-09-17T23:59:00Z"
    assert data["record_count"] == 11
    assert data["total_quantity"] == 100076
    assert data["serial_count"] == 6
    assert data["photo_count"] == 3
    assert data["model_count"] == 6
    assert data["categories"] == [
        {"name": "Handgun", "records": 3, "quantity": 7, "serial_count": 2, "missing_serial_count": 5},
        {"name": "Rifle", "records": 1, "quantity": 3, "serial_count": 1, "missing_serial_count": 2},
        {"name": "Shotgun", "records": 1, "quantity": 1, "serial_count": 0, "missing_serial_count": 1},
        {"name": "Machine gun", "records": 2, "quantity": 7, "serial_count": 1, "missing_serial_count": 6},
        {"name": "Ammunition", "records": 2, "quantity": 100050, "serial_count": 1, "missing_serial_count": 100049},
        {"name": "Other & custom", "records": 2, "quantity": 8, "serial_count": 1, "missing_serial_count": 7},
    ]
    assert sum(category["records"] for category in data["categories"]) == data["record_count"]
    assert sum(category["quantity"] for category in data["categories"]) == data["total_quantity"]


def test_multiple_serials_and_legacy_entries_use_quantity_for_coverage(setup):
    client, path = setup
    with connect(path) as connection:
        user_id = connection.execute("SELECT id FROM users WHERE username = 'verifier'").fetchone()["id"]
        log_id = insert_log(connection, user_id, "2026-09-17T12:00:00Z")
        insert_weapon(connection, log_id, "Rifle", 4, serial="R1", serials=["R1", "R2", "R3"],
                      model="R model", photo=photo_bytes())
        insert_weapon(connection, log_id, "Rifle", 2, serial="STALE-LEGACY", serials=[])
        insert_weapon(connection, log_id, "Rifle", 3, serial="  LEGACY-1  ")
        insert_weapon(connection, log_id, "Handgun", 2, serials=["H1", "H2"])
    data = collected(path, [log_id])
    assert data["record_count"] == 4
    assert data["total_quantity"] == 11
    assert data["serial_count"] == 6
    assert data["photo_count"] == 1
    assert data["model_count"] == 1
    assert data["categories"][0] == {
        "name": "Handgun", "records": 1, "quantity": 2, "serial_count": 2, "missing_serial_count": 0,
    }
    assert data["categories"][1] == {
        "name": "Rifle", "records": 3, "quantity": 9, "serial_count": 4, "missing_serial_count": 5,
    }
    assert sum(category["missing_serial_count"] for category in data["categories"]) == 5
    response = client.post("/api/logs/report.pdf", json={"log_ids": [log_id]})
    assert response.status_code == 200
    text = summary_page(response.content)
    assert "Recorded: 6 (54.5%)" in text
    assert "Not recorded: 5 (45.5%)" in text
    assert "Coverage counts individual units against total quantity, including ammunition." in text
    assert "Records with a photo: 1 | With name/model: 1" in text
    assert "Selected logs | Unverified and verified" in text
    status_text = text.split("Verification status", 1)[1].split("Serial-number coverage", 1)[0]
    assert "Unverified" in status_text and "Open" not in status_text


def test_partial_selection_and_duplicate_ids_do_not_include_other_logs(populated):
    client, path, own_ids, _ = populated
    selected = [own_ids[1]]
    data = collected(path, selected)
    assert data["operation_count"] == 1
    assert data["verified_count"] == 1
    assert data["open_count"] == 0
    assert data["record_count"] == 7
    assert data["total_quantity"] == 18
    assert data["serial_count"] == 4
    assert data["photo_count"] == 3
    assert data["model_count"] == 4
    assert data["period_start"] == data["period_end"] == "2026-09-05T00:00:00Z"
    assert data["categories"][4]["records"] == 0
    assert collected(path, selected * 3) == data
    response = client.post("/api/logs/report.pdf", json={"log_ids": selected * 3})
    assert response.status_code == 200
    text = summary_page(response.content)
    assert "100,076" not in text and "100,050" not in text


def test_download_is_pdf_attachment_with_own_aggregate_content(populated):
    client, _, own_ids, other_id = populated
    response = client.post("/api/logs/report.pdf", json={"log_ids": own_ids})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert re.fullmatch(r'attachment; filename="intrac-operation-summary-\d{4}-\d{2}-\d{2}\.pdf"',
                        response.headers["content-disposition"])
    assert response.headers["cache-control"] == "no-store"
    text = summary_page(response.content)
    assert "verifier" in text
    assert "100,076" in text
    assert "99,999" not in text
    for name in CATEGORIES:
        assert name in text
    assert "PRIVATE-OPERATION-NAME" not in text
    assert "PRIVATE-CUSTOM-TYPE" not in text
    assert "OTHER-SERIAL" not in text
    sign_in(client, "other")
    other = client.post("/api/logs/report.pdf", json={"log_ids": [other_id]})
    assert other.status_code == 200
    other_text = summary_page(other.content)
    assert "other" in other_text
    assert "99,999" in other_text
    assert "100,076" not in other_text


def test_report_route_requires_verifier(setup):
    client, _ = setup
    sign_in(client, "admin")
    assert client.post("/api/logs/report.pdf", json={"log_ids": [1]}).status_code == 403
    client.post("/api/auth/logout")
    assert client.post("/api/logs/report.pdf", json={"log_ids": [1]}).status_code == 401


def test_any_unknown_or_unowned_selection_rejects_the_whole_request(populated):
    client, _, own_ids, other_id = populated
    for selection in ([other_id], [own_ids[0], other_id], [999999], [own_ids[0], 999999]):
        response = client.post("/api/logs/report.pdf", json={"log_ids": selection})
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("body", [
    {}, {"log_ids": []}, {"log_ids": None}, {"log_ids": "1"},
    {"log_ids": [0]}, {"log_ids": [-1]}, {"log_ids": [True]}, {"log_ids": [1.0]},
    {"log_ids": ["1"]}, {"log_ids": [None]}, {"log_ids": [1], "username": "other"},
])
def test_invalid_report_selection_is_rejected(setup, body):
    client, _ = setup
    assert client.post("/api/logs/report.pdf", json=body).status_code == 422


def test_extreme_report_remains_one_letter_page_with_full_counts():
    data = zero_report()
    extreme = 999_999_999_999
    for key in ("operation_count", "verified_count", "open_count", "record_count", "total_quantity",
                "serial_count", "photo_count", "model_count"):
        data[key] = extreme
    data["period_start"] = "1900-01-01T00:00:00Z"
    data["period_end"] = "9999-12-31T23:59:59Z"
    for category in data["categories"]:
        for key in ("records", "quantity", "serial_count", "missing_serial_count"):
            category[key] = extreme
    username = "v" * 64
    text = single_letter_page(render_report(data, username, GENERATED_AT))
    assert f"{extreme:,}" in text
    assert username in text
    for name in CATEGORIES:
        assert name in text
