import hashlib
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from pypdf import PdfReader

from app.storage import connect
from test_logs import new_log, password_hash, photo_bytes, setup, sign_in
from test_report import single_letter_page, summary_page


@pytest.fixture
def photo_report(setup):
    client, path = setup
    with connect(path) as connection:
        connection.execute("UPDATE users SET first_name = ?, last_name = ? WHERE username = 'verifier'",
                           ("Élodie", "حمود"))
    first = new_log(client, operation_name="Opération بوابة", operator_name="Soldat علي",
                    location_name="Poste — بيروت")
    second = new_log(client, operation_name="Verified operation", operator_name="",
                     latitude=None, longitude=None, location_accuracy=None)
    saved = []
    for log, image_format, extension, mime_type, serials in [
        (first, "JPEG", "jpg", "image/jpeg", ["SN-α", "SN-ب"]),
        (first, "PNG", "png", "image/png", []),
        (second, "WEBP", "webp", "image/webp", ["LEGACY-7"]),
    ]:
        photo = photo_bytes(image_format, (7, 9))
        response = client.post(
            f"/api/logs/{log['id']}/weapons",
            data={"item_type": "Rifle", "name_model": "Modèle خاص", "quantity": "3",
                  "serial_numbers": json.dumps(serials)},
            files={"photo": (f"original.{extension}", photo, mime_type)},
        )
        assert response.status_code == 201, response.text
        weapon = response.json()
        saved.append({"filename": f"log-{log['id']}-weapon-{weapon['id']}.{extension}",
                      "content": photo, "mime_type": mime_type, "weapon_id": weapon["id"],
                      "log_id": log["id"], "serials": serials})
    with connect(path) as connection:
        connection.execute("UPDATE weapons SET serial_numbers = NULL, serial_number = ? WHERE id = ?",
                           ("  LEGACY-7  ", saved[-1]["weapon_id"]))
    response = client.post(f"/api/logs/{second['id']}/review",
                           json={"confirmed": True, "expected_weapon_count": 1})
    assert response.status_code == 200

    excluded = new_log(client, operation_name="EXCLUDED-OWN-OPERATION")
    response = client.post(f"/api/logs/{excluded['id']}/weapons", data={"item_type": "Handgun"},
                           files={"photo": ("excluded.png", photo_bytes(), "image/png")})
    assert response.status_code == 201
    sign_in(client, "other")
    other = new_log(client, operation_name="PRIVATE-OTHER-OPERATION")
    response = client.post(f"/api/logs/{other['id']}/weapons", data={"item_type": "Shotgun"},
                           files={"photo": ("other.png", photo_bytes(), "image/png")})
    assert response.status_code == 201
    sign_in(client)
    return client, path, [first["id"], second["id"]], saved, other["id"]


def test_selected_photos_are_embedded_once_with_original_bytes_and_mime(photo_report):
    client, _, log_ids, saved, other_id = photo_report
    response = client.post("/api/logs/report.pdf", json={"log_ids": log_ids * 2})
    assert response.status_code == 200, response.text
    text = summary_page(response.content)
    assert "Opération" not in text
    document = PdfReader(io.BytesIO(response.content))
    assert document.page_mode == "/UseNone"
    assert len(document.pages) > 1
    appendix_images = [image for page in document.pages[1:] for image in page.images]
    assert len(appendix_images) == len(saved)
    appendix_text = "\n".join(page.extract_text(extraction_mode="layout") for page in document.pages[1:])
    for value in ("Opération بوابة", "Verified operation", "LAF Soldier Name", "Soldat علي", "Location",
                  "Poste — بيروت", "Weapon type", "Rifle", "Name/model", "Modèle خاص",
                  "Quantity", "Serial numbers", "SN-α", "SN-ب", "LEGACY-7", "Recorded by", "Élodie حمود",
                  "Unverified", "Verified by", "Verified at"):
        assert value in appendix_text
    for omitted in ("46.8", "-100.8", "Coordinates", "Operation ID", "Weapon record ID", "SHA-256",
                    "Photo file", "Operation record created at", "Weapon record created at"):
        assert omitted not in appendix_text
    for excluded in ("EXCLUDED-OWN-OPERATION", "PRIVATE-OTHER-OPERATION"):
        assert excluded not in appendix_text
    attachments = list(document.attachment_list)
    expected_names = {photo["filename"] for photo in saved} | {"photo-metadata.json", "photo-metadata.txt"}
    assert len(attachments) == len(expected_names)
    assert {attachment.name for attachment in attachments} == expected_names
    files = {attachment.name: attachment for attachment in attachments}
    for photo in saved:
        attachment = files[photo["filename"]]
        assert attachment.content == photo["content"]
        assert attachment.subtype == f"/{photo['mime_type']}"
    assert files["photo-metadata.json"].subtype == "/application/json"
    assert files["photo-metadata.txt"].subtype == "/text/plain"

    rejected = client.post("/api/logs/report.pdf", json={"log_ids": [*log_ids, other_id]})
    assert rejected.status_code == 404
    assert rejected.headers["content-type"] == "application/json"


def test_photo_page_shows_location_once_and_hides_technical_and_empty_details(setup):
    client, _ = setup
    location = "46.800000, -100.800000"
    log = new_log(client, location_name=location, operator_name="")
    original = photo_bytes()
    response = client.post(
        f"/api/logs/{log['id']}/weapons", data={"item_type": "Handgun", "quantity": "2"},
        files={"photo": ("original.png", original, "image/png")},
    )
    assert response.status_code == 201
    weapon = response.json()
    report = client.post("/api/logs/report.pdf", json={"log_ids": [log["id"]]})
    assert report.status_code == 200
    document = PdfReader(io.BytesIO(report.content))
    assert len(document.pages) == 2
    visible = document.pages[1].extract_text()
    assert visible.count(location) == 1
    for value in ("Operation West Gate", "17 Sep 2026", "Handgun", "Quantity", "Serial numbers",
                  "Not recorded", "Recorded by", "Avery Jones", "Unverified"):
        assert value in visible
    for omitted in ("SHA-256", hashlib.sha256(original).hexdigest(), "Photo file", "image/png", "pixels",
                    "bytes", "Coordinates", "accuracy", "Operation ID", "Weapon record ID",
                    "LAF Soldier Name", "Name/model", "Verified by", "Verified at", "verifier",
                    "created at", "16:35", f"log-{log['id']}-weapon-{weapon['id']}.png"):
        assert omitted not in visible

    metadata = json.loads(document.attachments["photo-metadata.json"][0])
    entry = metadata["photos"][0]
    assert entry["log"]["location_accuracy"] == 12.5
    assert entry["log"]["recorded_by"]["username"] == "verifier"
    assert entry["photo"]["sha256"] == hashlib.sha256(original).hexdigest()


def test_photo_metadata_preserves_complete_log_weapon_and_image_context(photo_report):
    client, path, log_ids, saved, _ = photo_report
    before = datetime.now(timezone.utc)
    response = client.post("/api/logs/report.pdf", json={"log_ids": log_ids})
    after = datetime.now(timezone.utc)
    assert response.status_code == 200
    attachments = PdfReader(io.BytesIO(response.content)).attachments
    metadata = json.loads(attachments["photo-metadata.json"][0].decode("utf-8"))
    generated_at = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
    assert generated_at.utcoffset() == timedelta(0)
    assert before <= generated_at <= after
    assert metadata["generated_by"] == "verifier"
    assert len(metadata["photos"]) == len(saved)
    entries = {entry["filename"]: entry for entry in metadata["photos"]}
    with connect(path) as connection:
        for photo in saved:
            log = connection.execute("SELECT * FROM operation_logs WHERE id = ?", (photo["log_id"],)).fetchone()
            weapon = connection.execute("SELECT * FROM weapons WHERE id = ?", (photo["weapon_id"],)).fetchone()
            entry = entries[photo["filename"]]
            assert entry["log"] == {
                "id": log["id"], "operation_name": log["operation_name"],
                "occurred_at": log["occurred_at"], "created_at": log["created_at"],
                "laf_soldier_name": log["operator_name"], "location_name": log["location_name"],
                "latitude": log["latitude"], "longitude": log["longitude"],
                "location_accuracy": log["location_accuracy"],
                "status": "Verified" if log["status"] == "REVIEWED" else "Unverified",
                "verified_at": log["reviewed_at"], "verified_by": log["reviewed_by_name"],
                "recorded_by": {"username": "verifier", "first_name": "Élodie", "last_name": "حمود"},
            }
            assert entry["weapon"] == {
                "id": weapon["id"], "item_type": weapon["item_type"], "name_model": weapon["name_model"],
                "quantity": 3, "serial_numbers": photo["serials"], "created_at": weapon["created_at"],
            }
            assert entry["photo"] == {
                "content_type": photo["mime_type"], "size_bytes": len(photo["content"]),
                "width": 7, "height": 9, "sha256": hashlib.sha256(photo["content"]).hexdigest(),
            }

    readable = attachments["photo-metadata.txt"][0].decode("utf-8")
    for value in ("Opération بوابة", "Soldat علي", "Poste — بيروت", "Élodie", "حمود",
                  "Modèle خاص", "SN-α", "SN-ب", "LEGACY-7", "Verified", "Unverified"):
        assert value in readable
    for photo in saved:
        assert photo["filename"] in readable
    for excluded in ("EXCLUDED-OWN-OPERATION", "PRIVATE-OTHER-OPERATION"):
        assert excluded not in readable
        assert excluded not in json.dumps(metadata, ensure_ascii=False)


def test_selected_log_without_photos_remains_one_page_without_attachments(setup):
    client, _ = setup
    log = new_log(client)
    response = client.post(f"/api/logs/{log['id']}/weapons", data={"item_type": "Rifle"})
    assert response.status_code == 201
    report = client.post("/api/logs/report.pdf", json={"log_ids": [log["id"]]})
    assert report.status_code == 200
    assert "Records with a photo: 0" in single_letter_page(report.content)
    assert not PdfReader(io.BytesIO(report.content)).attachments


def test_long_fields_and_every_serial_flow_to_visible_continuation_pages(setup):
    client, _ = setup
    operation = "<OPERATION>&" + "N" * 148
    soldier = "<SOLDIER>&" + "S" * 150
    location = "<LOCATION>&" + "L" * 239
    model = "<MODEL>&" + "M" * 152
    serials = [f"SERIAL-{index:03d}-" + "A" * 149 for index in range(45)]
    log = new_log(client, operation_name=operation, operator_name=soldier, location_name=location)
    response = client.post(
        f"/api/logs/{log['id']}/weapons",
        data={"item_type": "Rifle", "name_model": model, "quantity": str(len(serials)),
              "serial_numbers": json.dumps(serials)},
        files={"photo": ("long.png", photo_bytes(), "image/png")},
    )
    assert response.status_code == 201, response.text
    report = client.post("/api/logs/report.pdf", json={"log_ids": [log["id"]]})
    assert report.status_code == 200
    summary_page(report.content)
    document = PdfReader(io.BytesIO(report.content))
    assert len(document.pages) >= 3
    assert sum(len(page.images) for page in document.pages[1:]) == 1
    visible = "".join("".join(page.extract_text().split()) for page in document.pages[1:])
    for value in (operation, soldier, location, model, *serials):
        assert "".join(value.split()) in visible

    def inside_page(text, matrix, text_matrix, font, size):
        if not text.strip():
            return
        x = text_matrix[4] * matrix[0] + text_matrix[5] * matrix[2] + matrix[4]
        y = text_matrix[4] * matrix[1] + text_matrix[5] * matrix[3] + matrix[5]
        assert 24 <= x <= 588, (text, x)
        assert 24 <= y <= 768, (text, y)

    for page in document.pages[1:]:
        page.extract_text(visitor_text=inside_page)


def test_visible_jpeg_respects_exif_orientation_and_preserves_original_attachment(setup):
    client, _ = setup
    image = Image.new("RGB", (12, 6), (20, 60, 80))
    exif = Image.Exif()
    exif[274] = 6
    stream = io.BytesIO()
    image.save(stream, "JPEG", exif=exif)
    original = stream.getvalue()
    log = new_log(client)
    response = client.post(
        f"/api/logs/{log['id']}/weapons", data={"item_type": "Rifle"},
        files={"photo": ("rotated.jpg", original, "image/jpeg")},
    )
    assert response.status_code == 201
    weapon = response.json()
    report = client.post("/api/logs/report.pdf", json={"log_ids": [log["id"]]})
    assert report.status_code == 200
    document = PdfReader(io.BytesIO(report.content))
    previews = [preview for page in document.pages[1:] for preview in page.images]
    assert len(previews) == 1
    assert previews[0].image.size == (6, 12)
    filename = f"log-{log['id']}-weapon-{weapon['id']}.jpg"
    assert document.attachments[filename] == [original]
