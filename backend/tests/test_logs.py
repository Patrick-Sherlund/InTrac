import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.storage import connect, hash_password


PASSWORD = "test-password-for-intrac"
LOG = {
    "operation_name": "Operation West Gate",
    "occurred_at": "2026-09-17T11:35:00-05:00",
    "location_name": "West Gate checkpoint",
    "latitude": 46.8,
    "longitude": -100.8,
    "location_accuracy": 12.5,
}


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def setup(tmp_path, password_hash):
    path = tmp_path / "logs.db"
    with TestClient(create_app(path)) as client:
        with connect(path) as connection:
            connection.executemany(
                "INSERT INTO users (first_name, last_name, username, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                [("Avery", "Jones", "verifier", password_hash, "VERIFIER"),
                 ("Morgan", "Lee", "other", password_hash, "VERIFIER"),
                 ("System", "Admin", "admin", password_hash, "ADMINISTRATOR")],
            )
        sign_in(client)
        yield client, path


def sign_in(client, username="verifier"):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def new_log(client, **changes):
    response = client.post("/api/logs", json={**LOG, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def photo_bytes(format="PNG", size=(5, 5)):
    stream = io.BytesIO()
    Image.new("RGB", size, (20, 60, 80)).save(stream, format=format)
    return stream.getvalue()


def test_log_create_list_detail_and_observed_operator(setup):
    client, _ = setup
    assert client.get("/api/logs").json() == []
    log = new_log(client, operation_name="  West Gate  ", location_name="  Checkpoint  ", operator_name="  Jordan Reed  ")
    assert log["operation_name"] == "West Gate"
    assert log["location_name"] == "Checkpoint"
    assert log["operator_name"] == "Jordan Reed"
    assert log["occurred_at"] == "2026-09-17T16:35:00Z"
    assert log["created_at"].endswith("Z")
    assert log["weapons"] == []
    assert log["weapon_count"] == 0 and log["total_quantity"] == 0
    assert client.get(f"/api/logs/{log['id']}").json() == log
    second = new_log(client, operation_name="South Gate")
    summaries = client.get("/api/logs").json()
    assert [item["id"] for item in summaries] == [second["id"], log["id"]]
    assert summaries[1]["operator_name"] == "Jordan Reed"
    assert all("weapons" not in item for item in summaries)


@pytest.mark.parametrize("changes,expected", [
    ({}, ""),
    ({"operator_name": ""}, ""),
    ({"operator_name": " \t "}, ""),
    ({"operator_name": "  " + "x" * 160 + "  "}, "x" * 160),
])
def test_optional_operator_name_and_trimmed_length_boundary(setup, changes, expected):
    client, _ = setup
    log = new_log(client, **changes)
    assert log["operator_name"] == expected
    assert client.get(f"/api/logs/{log['id']}").json()["operator_name"] == expected
    assert client.get("/api/logs").json()[0]["operator_name"] == expected


def test_log_manual_location_without_coordinates(setup):
    client, _ = setup
    log = new_log(client, latitude=None, longitude=None, location_accuracy=None)
    assert log["latitude"] is None and log["longitude"] is None
    assert log["location_accuracy"] is None


@pytest.mark.parametrize("changes", [
    {"operation_name": "  "}, {"operation_name": "x" * 161}, {"location_name": " "},
    {"location_name": "x" * 251}, {"occurred_at": "2026-09-17T11:35:00"},
    {"occurred_at": "invalid"}, {"occurred_at": 12345}, {"occurred_at": "12345"},
    {"latitude": 90.1}, {"longitude": -180.1}, {"latitude": "46.8"}, {"latitude": True},
    {"longitude": None}, {"latitude": None, "longitude": None}, {"location_accuracy": -1},
    {"operator_name": "x" * 161}, {"operator_name": None}, {"operator_name": 12},
    {"operator_name": True}, {"operator_name": []}, {"operator_name": {}}, {"user_id": 2},
])
def test_invalid_logs_not_saved(setup, changes):
    client, _ = setup
    assert client.post("/api/logs", json={**LOG, **changes}).status_code == 422
    assert client.get("/api/logs").json() == []


def test_role_and_log_ownership(setup):
    client, _ = setup
    log = new_log(client, operator_name="Morgan Lee")
    weapon = client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"},
                         files={"photo": ("photo.png", photo_bytes(), "image/png")}).json()
    sign_in(client, "other")
    assert client.get("/api/logs").json() == []
    assert client.get(f"/api/logs/{log['id']}").status_code == 404
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"}).status_code == 404
    assert client.get(weapon["photo_url"]).status_code == 404
    sign_in(client, "admin")
    assert client.get("/api/logs").status_code == 403
    assert client.post("/api/logs", json=LOG).status_code == 403
    assert client.get(f"/api/logs/{log['id']}").status_code == 403
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"}).status_code == 403
    assert client.get(weapon["photo_url"]).status_code == 403
    client.post("/api/auth/logout")
    assert client.get("/api/logs").status_code == 401
    assert client.post("/api/logs", json=LOG).status_code == 401
    assert client.get(weapon["photo_url"]).status_code == 401


def test_weapon_required_optional_fields_and_totals(setup):
    client, _ = setup
    log = new_log(client)
    url = f"/api/logs/{log['id']}/weapons"
    response = client.post(url, data={"item_type": " Ammunition ", "name_model": "  9 mm  ",
                                     "serial_number": "  SERIAL-25  ", "quantity": "25"})
    assert response.status_code == 201
    weapon = response.json()
    assert weapon["item_type"] == "Ammunition" and weapon["quantity"] == 25
    assert weapon["name_model"] == "9 mm" and weapon["serial_number"] == "SERIAL-25"
    assert weapon["serial_numbers"] == ["SERIAL-25"]
    assert weapon["photo_url"] is None
    minimum = client.post(url, data={"item_type": "Firearm"})
    assert minimum.status_code == 201
    assert minimum.json()["quantity"] == 1
    assert all(minimum.json()[name] == "" for name in ("name_model", "serial_number"))
    assert minimum.json()["serial_numbers"] == []
    detail = client.get(f"/api/logs/{log['id']}").json()
    assert detail["weapon_count"] == 2 and detail["total_quantity"] == 26
    assert detail["weapons"] == [weapon, minimum.json()]
    assert client.get("/api/logs").json()[0]["total_quantity"] == 26
    assert client.get(f"{url}/{weapon['id']}/photo").status_code == 404


@pytest.mark.parametrize("changes", [
    {"item_type": " "}, {"item_type": "x" * 81}, {"name_model": "x" * 161},
    {"serial_number": "x" * 161}, {"quantity": "0"},
    {"quantity": "-1"}, {"quantity": "100001"}, {"quantity": "1.5"}, {"quantity": "2.0"},
    {"quantity": "true"}, {"quantity": "1e2"}, {"quantity": "x" * 4500}, {"quantity": ""},
])
def test_invalid_weapons_not_saved(setup, changes):
    client, _ = setup
    log = new_log(client)
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm", **changes}).status_code == 422
    assert client.get(f"/api/logs/{log['id']}").json()["weapon_count"] == 0


def test_multiple_serial_numbers_preserve_order_and_survive_restart(setup):
    client, path = setup
    log = new_log(client)
    serials = ["SN-003", "SN-001", "x" * 160]
    response = client.post(f"/api/logs/{log['id']}/weapons", data={
        "item_type": "Rifle", "quantity": "4",
        "serial_numbers": json.dumps([" SN-003 ", "", " \t ", "SN-001", " " + serials[2] + " "]),
    })
    assert response.status_code == 201, response.text
    weapon = response.json()
    assert weapon["serial_numbers"] == serials
    assert weapon["serial_number"] == serials[0]
    assert weapon["quantity"] == 4
    with connect(path) as connection:
        stored = connection.execute("SELECT serial_number, serial_numbers FROM weapons WHERE id = ?", (weapon["id"],)).fetchone()
        assert json.loads(stored["serial_numbers"]) == serials
        assert stored["serial_number"] == serials[0]
    with TestClient(create_app(path)) as reopened:
        sign_in(reopened)
        detail = reopened.get(f"/api/logs/{log['id']}").json()
        assert detail["weapons"] == [weapon]
        assert detail["total_quantity"] == 4
        sign_in(reopened, "other")
        assert reopened.get(f"/api/logs/{log['id']}").status_code == 404
        assert reopened.post(f"/api/logs/{log['id']}/weapons", data={
            "item_type": "Rifle", "serial_numbers": '["OTHER"]',
        }).status_code == 404


@pytest.mark.parametrize("serial_numbers,quantity,message", [
    ("invalid", "2", "JSON array"), ("", "2", "JSON array"),
    ('"SERIAL"', "2", "list"), ('{"value":"SERIAL"}', "2", "list"),
    ("null", "2", "list"), ("true", "2", "list"),
    ('["SERIAL", 123]', "2", "string"), ('[false]', "2", "string"),
    ('[null]', "2", "string"), ('[["SERIAL"]]', "2", "string"),
    (json.dumps(["x" * 161]), "2", "160"),
    ('["SN-1", "sn-1"]', "2", "unique"),
    ('[" SN-1 ", "SN-1"]', "2", "unique"),
    ('["SN-1", "SN-2"]', "1", "exceed the quantity"),
])
def test_invalid_serial_lists_are_not_saved(setup, serial_numbers, quantity, message):
    client, _ = setup
    log = new_log(client)
    response = client.post(f"/api/logs/{log['id']}/weapons", data={
        "item_type": "Rifle", "quantity": quantity, "serial_numbers": serial_numbers,
    })
    assert response.status_code == 422, response.text
    assert message in response.json()["detail"]
    assert client.get(f"/api/logs/{log['id']}").json()["weapons"] == []


@pytest.mark.parametrize("serial_numbers", ["[]", '["", " "]'])
def test_empty_serial_list_is_explicit_and_overrides_legacy_value(setup, serial_numbers):
    client, path = setup
    log = new_log(client)
    response = client.post(f"/api/logs/{log['id']}/weapons", data={
        "item_type": "Rifle", "serial_number": "LEGACY", "serial_numbers": serial_numbers,
    })
    assert response.status_code == 201, response.text
    weapon = response.json()
    assert weapon["serial_numbers"] == []
    assert weapon["serial_number"] == ""
    with connect(path) as connection:
        stored = connection.execute("SELECT serial_numbers FROM weapons WHERE id = ?", (weapon["id"],)).fetchone()
        assert stored["serial_numbers"] == "[]"


def test_null_serial_lists_fall_back_to_legacy_values(setup):
    client, path = setup
    log = new_log(client)
    with connect(path) as connection:
        connection.executemany(
            "INSERT INTO weapons (log_id, item_type, serial_number, quantity, created_at) VALUES (?, 'Rifle', ?, 1, ?)",
            [(log["id"], "LEGACY-SN", log["created_at"]), (log["id"], "  ", log["created_at"])],
        )
    weapons = client.get(f"/api/logs/{log['id']}").json()["weapons"]
    assert [weapon["serial_numbers"] for weapon in weapons] == [["LEGACY-SN"], []]


@pytest.mark.parametrize("format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_valid_photo_and_restricted_response(setup, format, mime):
    client, _ = setup
    log = new_log(client)
    content = photo_bytes(format)
    response = client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"},
                           files={"photo": (f"photo.{format.lower()}", content, mime)})
    assert response.status_code == 201
    photo_url = response.json()["photo_url"]
    photo = client.get(photo_url)
    assert photo.status_code == 200 and photo.content == content
    assert photo.headers["content-type"] == mime
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.headers["cache-control"] == "no-store"
    other_log = new_log(client)
    assert client.get(photo_url.replace(f"/logs/{log['id']}/", f"/logs/{other_log['id']}/")).status_code == 404


@pytest.mark.parametrize("content,mime", [
    (b"not an image", "image/jpeg"), (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
    (photo_bytes(), "image/jpeg"), (photo_bytes("GIF"), "image/gif"), (photo_bytes("JPEG")[:80], "image/jpeg"),
])
def test_invalid_photos_are_atomic(setup, content, mime):
    client, path = setup
    log = new_log(client)
    response = client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"},
                           files={"photo": ("photo.png", content, mime)})
    assert response.status_code == 422
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM weapons").fetchone()[0] == 0


def test_oversized_photos_rejected(setup, monkeypatch):
    client, _ = setup
    log = new_log(client)
    url = f"/api/logs/{log['id']}/weapons"
    content = b"x" * (8 * 1024 * 1024 + 1)
    assert client.post(url, data={"item_type": "Firearm"}, files={"photo": ("photo.png", content, "image/png")}).status_code == 413
    monkeypatch.setattr("app.logs.MAX_PHOTO_PIXELS", 20)
    response = client.post(url, data={"item_type": "Firearm"}, files={"photo": ("photo.png", photo_bytes(size=(5, 5)), "image/png")})
    assert response.status_code == 422
    assert "20 megapixels" in response.json()["detail"]
    assert client.get(f"/api/logs/{log['id']}").json()["weapons"] == []


def test_persistence_and_existing_accounts_are_preserved(setup):
    client, path = setup
    log = new_log(client, operator_name="  Jordan Reed  ")
    content = photo_bytes()
    weapon = client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"},
                         files={"photo": ("photo.png", content, "image/png")}).json()
    with TestClient(create_app(path)) as reopened:
        sign_in(reopened)
        detail = reopened.get(f"/api/logs/{log['id']}").json()
        assert detail["weapons"] == [weapon]
        assert detail["operator_name"] == "Jordan Reed"
        assert reopened.get(weapon["photo_url"]).content == content
        sign_in(reopened, "admin")
        assert reopened.get("/api/auth/me").json()["role"] == "ADMINISTRATOR"
