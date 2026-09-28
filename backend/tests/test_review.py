import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import connect
from test_logs import new_log, password_hash, photo_bytes, setup, sign_in


def review(client, log_id, expected_weapon_count=0, **changes):
    return client.post(
        f"/api/logs/{log_id}/review",
        json={"confirmed": True, "expected_weapon_count": expected_weapon_count, **changes},
    )


def assert_open(log):
    assert log["status"] == "OPEN"
    assert log["reviewed_at"] is None
    assert log["reviewed_by_name"] is None


def test_review_metadata_full_detail_and_photo_access(setup):
    client, _ = setup
    log = new_log(client, operator_name="  Jordan Reed  ")
    assert_open(log)
    assert_open(client.get("/api/logs").json()[0])
    assert_open(client.get(f"/api/logs/{log['id']}").json())
    photo = photo_bytes()
    weapon_response = client.post(
        f"/api/logs/{log['id']}/weapons",
        data={"item_type": "Ammunition", "quantity": "25", "serial_numbers": '["AM-1", "AM-2"]'},
        files={"photo": ("photo.png", photo, "image/png")},
    )
    assert weapon_response.status_code == 201
    weapon = weapon_response.json()
    before_review = datetime.now(timezone.utc)
    response = review(client, log["id"], expected_weapon_count=1)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["status"] == "REVIEWED"
    assert reviewed["operator_name"] == "Jordan Reed"
    assert reviewed["reviewed_by_name"] == "Avery Jones"
    reviewed_at = datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
    assert before_review <= reviewed_at <= datetime.now(timezone.utc)
    assert reviewed["weapons"] == [weapon]
    assert reviewed["weapons"][0]["serial_numbers"] == ["AM-1", "AM-2"]
    assert reviewed["weapon_count"] == 1
    assert reviewed["total_quantity"] == 25
    for field, value in log.items():
        if field not in {"weapons", "weapon_count", "total_quantity", "status", "reviewed_at", "reviewed_by_name"}:
            assert reviewed[field] == value
    assert client.get(f"/api/logs/{log['id']}").json() == reviewed
    assert client.get("/api/logs").json()[0] == {key: value for key, value in reviewed.items() if key != "weapons"}
    saved_photo = client.get(weapon["photo_url"])
    assert saved_photo.status_code == 200
    assert saved_photo.content == photo
    rejected = client.post(f"/api/logs/{log['id']}/weapons", data={
        "item_type": "Rifle", "quantity": "2", "serial_numbers": '["SN-1", "SN-2"]',
    })
    assert rejected.status_code == 409
    assert client.get(f"/api/logs/{log['id']}").json()["weapons"] == [weapon]


def test_empty_review_is_idempotent_and_survives_restart(setup):
    client, path = setup
    log = new_log(client)
    response = review(client, log["id"])
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["status"] == "REVIEWED"
    assert reviewed["weapons"] == []
    with connect(path) as connection:
        connection.execute("UPDATE users SET first_name = 'Renamed' WHERE username = 'verifier'")
    retry = review(client, log["id"], expected_weapon_count=123)
    assert retry.status_code == 200
    assert retry.json() == reviewed
    with TestClient(create_app(path)) as reopened:
        sign_in(reopened)
        assert reopened.get(f"/api/logs/{log['id']}").json() == reviewed
        assert review(reopened, log["id"], expected_weapon_count=999).json() == reviewed
        assert reopened.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"}).status_code == 409


@pytest.mark.parametrize("body", [
    {},
    {"confirmed": True},
    {"expected_weapon_count": 0},
    {"confirmed": False, "expected_weapon_count": 0},
    {"confirmed": 1, "expected_weapon_count": 0},
    {"confirmed": 0, "expected_weapon_count": 0},
    {"confirmed": "true", "expected_weapon_count": 0},
    {"confirmed": "yes", "expected_weapon_count": 0},
    {"confirmed": None, "expected_weapon_count": 0},
    {"confirmed": True, "expected_weapon_count": -1},
    {"confirmed": True, "expected_weapon_count": 0.0},
    {"confirmed": True, "expected_weapon_count": "0"},
    {"confirmed": True, "expected_weapon_count": False},
    {"confirmed": True, "expected_weapon_count": None},
    {"confirmed": True, "expected_weapon_count": 0, "status": "REVIEWED"},
    {"confirmed": True, "expected_weapon_count": 0, "reviewed_by_name": "Someone Else"},
    {"confirmed": True, "expected_weapon_count": 0, "reviewed_at": "2026-01-01T00:00:00Z"},
])
def test_review_requires_explicit_confirmation_count_and_no_extra_fields(setup, body):
    client, _ = setup
    log = new_log(client)
    response = client.post(f"/api/logs/{log['id']}/review", json=body)
    assert response.status_code == 422, response.text
    assert_open(client.get(f"/api/logs/{log['id']}").json())


def test_stale_count_does_not_close_log(setup):
    client, _ = setup
    log = new_log(client)
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"}).status_code == 201
    response = review(client, log["id"], expected_weapon_count=0)
    assert response.status_code == 409
    assert_open(client.get(f"/api/logs/{log['id']}").json())
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Ammunition"}).status_code == 201
    assert review(client, log["id"], expected_weapon_count=2).status_code == 200
    assert client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Firearm"}).status_code == 409
    detail = client.get(f"/api/logs/{log['id']}").json()
    assert detail["weapon_count"] == 2


def test_review_only_owner_verifier_can_review(setup):
    client, _ = setup
    log = new_log(client)
    assert review(client, log["id"] + 1000).status_code == 404
    sign_in(client, "other")
    assert review(client, log["id"]).status_code == 404
    sign_in(client, "admin")
    assert review(client, log["id"]).status_code == 403
    client.post("/api/auth/logout")
    assert review(client, log["id"]).status_code == 401
    sign_in(client)
    assert_open(client.get(f"/api/logs/{log['id']}").json())


def test_review_prevents_an_upload_already_in_progress(setup, monkeypatch):
    client, path = setup
    log = new_log(client)
    import app.logs

    original_validate = app.logs.validate_photo
    validating = Event()
    release_upload = Event()

    def delayed_validate(photo):
        result = original_validate(photo)
        validating.set()
        assert release_upload.wait(timeout=10), "Review did not finish while upload was paused"
        return result

    monkeypatch.setattr(app.logs, "validate_photo", delayed_validate)
    with TestClient(create_app(path)) as uploader, ThreadPoolExecutor(max_workers=1) as executor:
        uploader.cookies.update(client.cookies)
        pending = executor.submit(
            uploader.post,
            f"/api/logs/{log['id']}/weapons",
            data={"item_type": "Firearm"},
            files={"photo": ("photo.png", photo_bytes(), "image/png")},
        )
        try:
            assert validating.wait(timeout=5), "Upload did not reach validation"
            response = review(client, log["id"])
            assert response.status_code == 200, response.text
        finally:
            release_upload.set()
        assert pending.result(timeout=5).status_code == 409
    detail = client.get(f"/api/logs/{log['id']}").json()
    assert detail["status"] == "REVIEWED"
    assert detail["weapons"] == []


def test_existing_database_migrates_without_losing_logs_or_photos(tmp_path, password_hash):
    path = tmp_path / "legacy.db"
    photo = photo_bytes()
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE, password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMINISTRATOR', 'VERIFIER'))
            );
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                operation_name TEXT NOT NULL, occurred_at TEXT NOT NULL, created_at TEXT NOT NULL,
                operator_name TEXT NOT NULL, location_name TEXT NOT NULL,
                latitude REAL, longitude REAL, location_accuracy REAL
            );
            CREATE TABLE weapons (
                id INTEGER PRIMARY KEY, log_id INTEGER NOT NULL REFERENCES operation_logs(id),
                item_type TEXT NOT NULL, name_model TEXT NOT NULL DEFAULT '',
                serial_number TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 100000),
                condition TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                photo BLOB, photo_content_type TEXT
            );
        """)
        connection.execute(
            "INSERT INTO users VALUES (7, 'Avery', 'Jones', 'verifier', ?, 'VERIFIER')", (password_hash,)
        )
        connection.execute(
            "INSERT INTO operation_logs VALUES (42, 7, 'Legacy operation', '2026-09-01T12:00:00Z', "
            "'2026-09-01T12:01:00Z', 'Avery Jones', 'Checkpoint', 46.8, -100.8, 12.5)"
        )
        connection.execute(
            "INSERT INTO weapons VALUES (19, 42, 'Firearm', 'Original model', 'SERIAL-123', 1, 'Good', "
            "'2026-09-01T12:02:00Z', ?, 'image/png')", (photo,)
        )
        original_user = connection.execute("SELECT * FROM users").fetchone()
        original_log = connection.execute("SELECT * FROM operation_logs").fetchone()
        original_weapon = connection.execute("SELECT * FROM weapons").fetchone()
    with TestClient(create_app(path)) as client:
        sign_in(client)
        response = client.get("/api/logs/42")
        assert response.status_code == 200
        migrated = response.json()
        assert_open(migrated)
        assert migrated["operation_name"] == "Legacy operation"
        assert migrated["weapon_count"] == 1
        assert migrated["weapons"][0]["serial_number"] == "SERIAL-123"
        assert migrated["weapons"][0]["serial_numbers"] == ["SERIAL-123"]
        saved_photo = client.get(migrated["weapons"][0]["photo_url"])
        assert saved_photo.status_code == 200 and saved_photo.content == photo
        with connect(path) as connection:
            assert tuple(connection.execute("SELECT * FROM users").fetchone()) == original_user
            assert tuple(connection.execute("SELECT id, user_id, operation_name, occurred_at, created_at, operator_name, "
                                            "location_name, latitude, longitude, location_accuracy FROM operation_logs").fetchone()) == original_log
            assert tuple(connection.execute("SELECT id, log_id, item_type, name_model, serial_number, quantity, condition, "
                                            "created_at, photo, photo_content_type FROM weapons").fetchone()) == original_weapon
            assert json.loads(connection.execute("SELECT serial_numbers FROM weapons").fetchone()[0]) == ["SERIAL-123"]
        reviewed = review(client, 42, expected_weapon_count=1)
        assert reviewed.status_code == 200
    with TestClient(create_app(path)) as reopened:
        sign_in(reopened)
        assert reopened.get("/api/logs/42").json() == reviewed.json()
