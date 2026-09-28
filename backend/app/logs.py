import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .report import collect_report, render_report
from .report_attachments import embed_report_photos
from .storage import connect, weapon_serial_numbers


MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
LOG_SUMMARY_QUERY = """
    SELECT operation_logs.*, COUNT(weapons.id) AS weapon_count,
           COALESCE(SUM(weapons.quantity), 0) AS total_quantity
    FROM operation_logs LEFT JOIN weapons ON weapons.log_id = operation_logs.id
"""
WEAPON_COLUMNS = "id, log_id, item_type, name_model, serial_number, serial_numbers, quantity, created_at, photo_content_type"


class LogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_name: str = Field(min_length=1, max_length=160)
    operator_name: str = Field(default="", max_length=160)
    occurred_at: AwareDatetime
    location_name: str = Field(min_length=1, max_length=250)
    latitude: float | None = Field(default=None, ge=-90, le=90, strict=True, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, strict=True, allow_inf_nan=False)
    location_accuracy: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)

    @field_validator("operation_name", "operator_name", "location_name", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("occurred_at", mode="before")
    @classmethod
    def require_timestamp(cls, value):
        if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}[Tt]", value):
            raise ValueError("Use an ISO date and time with a timezone")
        return value

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        if self.location_accuracy is not None and self.latitude is None:
            raise ValueError("Location accuracy requires coordinates")
        return self


class LogSummary(BaseModel):
    id: int
    operation_name: str
    occurred_at: AwareDatetime
    created_at: AwareDatetime
    operator_name: str
    location_name: str
    latitude: float | None
    longitude: float | None
    location_accuracy: float | None
    weapon_count: int
    total_quantity: int
    status: Literal["OPEN", "REVIEWED"]
    reviewed_at: AwareDatetime | None
    reviewed_by_name: str | None


class Weapon(BaseModel):
    id: int
    log_id: int
    item_type: str
    name_model: str
    serial_number: str
    serial_numbers: list[str]
    quantity: int
    created_at: AwareDatetime
    photo_url: str | None


class LogDetail(LogSummary):
    weapons: list[Weapon]


class LogReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = Field(strict=True)
    expected_weapon_count: int = Field(ge=0, strict=True)

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value):
        if not value:
            raise ValueError("Confirm that this log is accurate before verifying it")
        return value


class ReportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1)

    @field_validator("log_ids")
    @classmethod
    def unique_ids(cls, value):
        return list(dict.fromkeys(value))


class WeaponCreate(BaseModel):
    item_type: str = Field(min_length=1, max_length=80)
    name_model: str = Field(default="", max_length=160)
    serial_number: str = Field(default="", max_length=160)
    serial_numbers: list[Annotated[str, Field(strict=True, max_length=160)]] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1, le=100000, strict=True)

    @model_validator(mode="before")
    @classmethod
    def use_legacy_serial_number(cls, values):
        if values.get("serial_numbers") is None:
            values["serial_numbers"] = [values.get("serial_number", "")]
        return values

    @field_validator("serial_numbers", mode="before")
    @classmethod
    def parse_serial_numbers(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, RecursionError):
                raise ValueError("Serial numbers must be a JSON array of text values") from None
        if not isinstance(value, list):
            raise ValueError("Serial numbers must be a list of text values")
        return [item.strip() if isinstance(item, str) else item for item in value
                if not isinstance(item, str) or item.strip()]

    @field_validator("item_type", "name_model", "serial_number", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("quantity", mode="before")
    @classmethod
    def whole_number(cls, value):
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,6}", value.strip()):
            return int(value.strip())
        raise ValueError("Quantity must be a whole number from 1 to 100000")

    @model_validator(mode="after")
    def validate_serial_count(self):
        if len({value.casefold() for value in self.serial_numbers}) != len(self.serial_numbers):
            raise ValueError("Each serial number must be unique within this entry")
        if len(self.serial_numbers) > self.quantity:
            raise ValueError("The number of serial numbers cannot exceed the quantity")
        return self


def weapon_response(row) -> Weapon:
    photo_url = f"/api/logs/{row['log_id']}/weapons/{row['id']}/photo" if row["photo_content_type"] else None
    values = dict(row)
    values["serial_numbers"] = weapon_serial_numbers(row)
    values["serial_number"] = next(iter(values["serial_numbers"]), "")
    return Weapon(**values, photo_url=photo_url)


def validate_photo(photo: UploadFile | None):
    if photo is None:
        return None, None
    content = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="The photo must be 8 MB or smaller.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            content_type = PHOTO_TYPES.get(image.format)
            if content_type is None or photo.content_type != content_type:
                raise HTTPException(status_code=422, detail="Upload a valid JPEG, PNG, or WebP photo with its matching file type.")
            if image.width * image.height > MAX_PHOTO_PIXELS:
                raise HTTPException(status_code=422, detail="The photo must be 20 megapixels or smaller.")
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="The photo could not be read. Upload a valid JPEG, PNG, or WebP image.") from None
    return content, content_type


async def form_quantity(request: Request):
    # A missing quantity defaults to one; a submitted empty value must fail validation.
    return (await request.form()).get("quantity", "1")


async def form_serial_numbers(request: Request):
    return (await request.form()).get("serial_numbers")


def logs_router(path: Path, current_user) -> APIRouter:
    router = APIRouter(prefix="/api/logs")

    def verifier(user=Depends(current_user)):
        if user.role != "VERIFIER":
            raise HTTPException(status_code=403, detail="Only verifiers can access operation logs.")
        return user

    def owned_log(connection, log_id: int, user_id: int):
        row = connection.execute(
            LOG_SUMMARY_QUERY + " WHERE operation_logs.id = ? AND operation_logs.user_id = ? GROUP BY operation_logs.id",
            (log_id, user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Operation log not found.")
        return row

    def log_detail(connection, row):
        weapons = connection.execute(
            f"SELECT {WEAPON_COLUMNS} FROM weapons WHERE log_id = ? ORDER BY created_at, id", (row["id"],)
        ).fetchall()
        return LogDetail(**dict(row), weapons=[weapon_response(weapon) for weapon in weapons])

    def require_open(row):
        if row["status"] == "REVIEWED":
            raise HTTPException(status_code=409, detail="This log has been verified and closed. Weapons can no longer be added.")

    @router.get("", response_model=list[LogSummary])
    def list_logs(user=Depends(verifier)):
        with connect(path) as connection:
            rows = connection.execute(
                LOG_SUMMARY_QUERY + " WHERE operation_logs.user_id = ? GROUP BY operation_logs.id "
                "ORDER BY operation_logs.created_at DESC, operation_logs.id DESC",
                (user.id,),
            ).fetchall()
        return [LogSummary(**dict(row)) for row in rows]

    @router.post("", response_model=LogDetail, status_code=201)
    def create_log(new_log: LogCreate, user=Depends(verifier)):
        values = new_log.model_dump()
        values["occurred_at"] = new_log.occurred_at.astimezone(timezone.utc).isoformat()
        values["created_at"] = datetime.now(timezone.utc).isoformat()
        with connect(path) as connection:
            cursor = connection.execute(
                "INSERT INTO operation_logs (user_id, operation_name, occurred_at, created_at, operator_name, "
                "location_name, latitude, longitude, location_accuracy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user.id, values["operation_name"], values["occurred_at"], values["created_at"], values["operator_name"],
                 values["location_name"], values["latitude"], values["longitude"], values["location_accuracy"]),
            )
            log_id = cursor.lastrowid
        return LogDetail(**values, id=log_id, weapon_count=0, total_quantity=0, weapons=[],
                         status="OPEN", reviewed_at=None, reviewed_by_name=None)

    @router.post("/report.pdf")
    def operation_report(selection: ReportSelection, user=Depends(verifier)):
        generated_at = datetime.now(timezone.utc)
        with connect(path) as connection:
            connection.execute("BEGIN")
            data = collect_report(connection, user.id, selection.log_ids)
            pdf = render_report(data, user.username, generated_at)
            pdf = embed_report_photos(pdf, connection, user.id, selection.log_ids, user.username, generated_at)
        filename = f"intrac-operation-summary-{generated_at:%Y-%m-%d}.pdf"
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @router.get("/{log_id}", response_model=LogDetail)
    def get_log(log_id: int, user=Depends(verifier)):
        with connect(path) as connection:
            connection.execute("BEGIN")
            return log_detail(connection, owned_log(connection, log_id, user.id))

    @router.post("/{log_id}/review", response_model=LogDetail)
    def review_log(log_id: int, review: LogReview, user=Depends(verifier)):
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = owned_log(connection, log_id, user.id)
            if row["status"] == "REVIEWED":
                return log_detail(connection, row)
            if row["weapon_count"] != review.expected_weapon_count:
                raise HTTPException(status_code=409, detail="This log has changed. Reload it and check the latest weapon list before confirming.")
            connection.execute(
                "UPDATE operation_logs SET status = 'REVIEWED', reviewed_at = ?, reviewed_by_name = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), f"{user.first_name} {user.last_name}", log_id),
            )
            return log_detail(connection, owned_log(connection, log_id, user.id))

    @router.post("/{log_id}/weapons", response_model=Weapon, status_code=201)
    def create_weapon(
        log_id: int,
        item_type: str = Form(...),
        name_model: str = Form(""),
        serial_number: str = Form(""),
        serial_numbers=Depends(form_serial_numbers),
        quantity=Depends(form_quantity),
        photo: UploadFile | None = File(None),
        user=Depends(verifier),
    ):
        with connect(path) as connection:
            require_open(owned_log(connection, log_id, user.id))
        try:
            weapon = WeaponCreate(item_type=item_type, name_model=name_model, serial_number=serial_number,
                                  serial_numbers=serial_numbers, quantity=quantity)
        except ValidationError as error:
            detail = " ".join(f"{(item['loc'][0] if item['loc'] else 'weapon').replace('_', ' ').capitalize()}: {item['msg']}."
                              for item in error.errors())
            raise HTTPException(status_code=422, detail=detail) from None
        content, content_type = validate_photo(photo)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_open(owned_log(connection, log_id, user.id))
            cursor = connection.execute(
                "INSERT INTO weapons (log_id, item_type, name_model, serial_number, serial_numbers, quantity, "
                "created_at, photo, photo_content_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (log_id, weapon.item_type, weapon.name_model, next(iter(weapon.serial_numbers), ""),
                 json.dumps(weapon.serial_numbers), weapon.quantity,
                 datetime.now(timezone.utc).isoformat(), content, content_type),
            )
            row = connection.execute(f"SELECT {WEAPON_COLUMNS} FROM weapons WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return weapon_response(row)

    @router.get("/{log_id}/weapons/{weapon_id}/photo")
    def get_photo(log_id: int, weapon_id: int, user=Depends(verifier)):
        with connect(path) as connection:
            row = connection.execute(
                "SELECT weapons.photo, weapons.photo_content_type FROM weapons JOIN operation_logs ON operation_logs.id = weapons.log_id "
                "WHERE weapons.id = ? AND weapons.log_id = ? AND operation_logs.user_id = ?",
                (weapon_id, log_id, user.id),
            ).fetchone()
        if row is None or row["photo"] is None:
            raise HTTPException(status_code=404, detail="Photo not found.")
        return Response(content=row["photo"], media_type=row["photo_content_type"], headers={"X-Content-Type-Options": "nosniff"})

    return router
