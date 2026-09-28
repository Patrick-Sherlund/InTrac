import io
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.storage import weapon_serial_numbers


CATEGORIES = ("Handgun", "Rifle", "Shotgun", "Machine gun", "Ammunition", "Other & custom")
TYPE_GROUPS = {
    "handgun": "Handgun", "pistol": "Handgun", "revolver": "Handgun",
    "rifle": "Rifle", "shotgun": "Shotgun", "machine gun": "Machine gun",
    "submachine gun": "Machine gun", "ammunition": "Ammunition",
}


def collect_report(connection, user_id: int, log_ids: list[int]) -> dict:
    selected_ids = list(dict.fromkeys(log_ids))
    selection = json.dumps(selected_ids)
    operations = connection.execute(
        "SELECT COUNT(*) AS operation_count, COALESCE(SUM(status = 'REVIEWED'), 0) AS verified_count, "
        "COALESCE(SUM(status = 'OPEN'), 0) AS open_count, MIN(occurred_at) AS period_start, "
        "MAX(occurred_at) AS period_end FROM operation_logs "
        "WHERE user_id = ? AND id IN (SELECT value FROM json_each(?))", (user_id, selection),
    ).fetchone()
    if operations["operation_count"] != len(selected_ids):
        raise HTTPException(status_code=404, detail="One or more selected logs are unavailable. Reload your logs and select them again.")

    connection.create_function("has_text", 1, lambda value: bool(value and value.strip()))
    connection.create_function("count_serial_numbers", 2, lambda values, legacy: len(weapon_serial_numbers(
        {"serial_numbers": values, "serial_number": legacy},
    )))
    groups = connection.execute(
        "SELECT weapons.item_type, COUNT(*) AS records, SUM(weapons.quantity) AS quantity, "
        "SUM(count_serial_numbers(weapons.serial_numbers, weapons.serial_number)) AS serial_count, "
        "SUM(weapons.photo IS NOT NULL) AS photo_count, SUM(has_text(weapons.name_model)) AS model_count "
        "FROM weapons JOIN operation_logs ON operation_logs.id = weapons.log_id "
        "WHERE operation_logs.user_id = ? AND operation_logs.id IN (SELECT value FROM json_each(?)) "
        "GROUP BY weapons.item_type", (user_id, selection),
    ).fetchall()
    categories = {name: {"name": name, "records": 0, "quantity": 0, "serial_count": 0, "missing_serial_count": 0}
                  for name in CATEGORIES}
    report = dict(operations)
    report.update(record_count=0, total_quantity=0, serial_count=0, photo_count=0, model_count=0)
    for group in groups:
        normalized_type = " ".join(group["item_type"].casefold().split())
        category = categories[TYPE_GROUPS.get(normalized_type, "Other & custom")]
        for key in ("records", "quantity", "serial_count"):
            category[key] += group[key]
        category["missing_serial_count"] += group["quantity"] - group["serial_count"]
        report["record_count"] += group["records"]
        report["total_quantity"] += group["quantity"]
        for key in ("serial_count", "photo_count", "model_count"):
            report[key] += group[key]
    report["categories"] = list(categories.values())
    return report


def render_report(data: dict, username: str, generated_at: datetime) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, pageCompression=1)
    pdf.setTitle("InTrac - Operation summary")
    pdf.setAuthor("InTrac")
    navy = HexColor("#183746")
    teal = HexColor("#197765")
    muted = HexColor("#58717D")
    rule = HexColor("#DCE5E8")
    pale = HexColor("#F2F6F7")
    left, right = 42, 570
    width = right - left

    def text(value, x, y, size=9, font="Helvetica", color=navy, max_width=None, align="left"):
        value = str(value)
        if max_width is not None:
            actual_width = stringWidth(value, font, size)
            if actual_width > max_width:
                size *= max_width / actual_width
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        if align == "right":
            pdf.drawRightString(x, y, value)
        else:
            pdf.drawString(x, y, value)

    def number(value):
        return f"{value:,}"

    def percent(value):
        return f"{value / data['total_quantity']:.1%}" if data["total_quantity"] else "N/A"

    def date(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y, %H:%M")

    pdf.setFillColor(navy)
    pdf.rect(0, 676, 612, 116, fill=1, stroke=0)
    pdf.setFillColor(teal)
    pdf.rect(left, 768, 30, 3, fill=1, stroke=0)
    text("InTrac", left, 746, 15, "Helvetica-Bold", white)
    text("Operation summary", left, 713, 27, "Helvetica-Bold", white)
    text("Selected logs | Unverified and verified", left, 693, 10, color=HexColor("#D0E1E5"))
    timestamp = generated_at.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    text(f"Generated {timestamp}", left, 654, color=muted)
    safe_username = username.encode("ascii", "replace").decode()
    text(f"Account: {safe_username}", left, 637, max_width=width)
    period = f"{date(data['period_start'])} - {date(data['period_end'])}" if data["period_start"] else "No operations"
    text(f"Operation period (UTC): {period}", left, 617, color=muted, max_width=width)

    text("OVERVIEW", left, 587, 9, "Helvetica-Bold", teal)
    metric_width = (width - 24) / 3
    for index, (label, value) in enumerate((
        ("Operations", data["operation_count"]), ("Weapon records", data["record_count"]),
        ("Total recorded quantity", data["total_quantity"]),
    )):
        x = left + index * (metric_width + 12)
        pdf.setFillColor(pale)
        pdf.roundRect(x, 508, metric_width, 66, 5, fill=1, stroke=0)
        text(label, x + 12, 554, 9, color=muted, max_width=metric_width - 24)
        text(number(value), x + 12, 525, 25, "Helvetica-Bold", max_width=metric_width - 24)
    text("Total quantity includes ammunition.", left, 493, 8, color=muted)

    text("Verification status", left, 468, 11, "Helvetica-Bold")
    for index, (label, value) in enumerate((("Verified", data["verified_count"]), ("Unverified", data["open_count"]))):
        x = left + index * 270
        pdf.setFillColor(HexColor("#EDF7F1") if index == 0 else pale)
        pdf.roundRect(x, 426, 258, 29, 4, fill=1, stroke=0)
        text(label, x + 12, 436, 9, color=teal if index == 0 else muted)
        text(number(value), x + 246, 435, 12, "Helvetica-Bold", max_width=150, align="right")

    text("Serial-number coverage", left, 404, 11, "Helvetica-Bold")
    pdf.setFillColor(rule)
    pdf.roundRect(left, 384, width, 8, 3, fill=1, stroke=0)
    if data["total_quantity"] and data["serial_count"]:
        pdf.setFillColor(teal)
        pdf.roundRect(left, 384, width * data["serial_count"] / data["total_quantity"], 8, 3, fill=1, stroke=0)
    missing = data["total_quantity"] - data["serial_count"]
    text(f"Recorded: {number(data['serial_count'])} ({percent(data['serial_count'])})", left, 367, 9, max_width=258)
    text(f"Not recorded: {number(missing)} ({percent(missing)})", left + 270, 367, 9, max_width=258)
    text("Coverage counts individual units against total quantity, including ammunition.", left, 353, 8, color=muted)

    text("Recorded items by type", left, 329, 11, "Helvetica-Bold")
    edges = (42, 154, 258, 362, 466, 570)
    pdf.setFillColor(navy)
    pdf.rect(left, 293, width, 25, fill=1, stroke=0)
    for index, label in enumerate(("Type", "Records", "Quantity", "Serial recorded", "Not recorded")):
        text(label, edges[index] + 10 if index == 0 else edges[index + 1] - 10, 302, 8, "Helvetica-Bold", white,
             max_width=edges[index + 1] - edges[index] - 20, align="left" if index == 0 else "right")
    for row_index, category in enumerate(data["categories"]):
        bottom = 293 - (row_index + 1) * 23
        if row_index % 2 == 0:
            pdf.setFillColor(pale)
            pdf.rect(left, bottom, width, 23, fill=1, stroke=0)
        values = (category["name"], number(category["records"]), number(category["quantity"]),
                  number(category["serial_count"]), number(category["missing_serial_count"]))
        for index, value in enumerate(values):
            text(value, edges[index] + 10 if index == 0 else edges[index + 1] - 10, bottom + 8, 9,
                 max_width=edges[index + 1] - edges[index] - 20, align="left" if index == 0 else "right")
    pdf.setStrokeColor(rule)
    pdf.line(left, 155, right, 155)
    for index, value in enumerate(("Total", number(data["record_count"]), number(data["total_quantity"]),
                                   number(data["serial_count"]), number(missing))):
        text(value, edges[index] + 10 if index == 0 else edges[index + 1] - 10, 139, 9, "Helvetica-Bold",
             max_width=edges[index + 1] - edges[index] - 20, align="left" if index == 0 else "right")

    text(f"Records with a photo: {number(data['photo_count'])} | With name/model: {number(data['model_count'])}",
         left, 116, 9, max_width=width)
    pdf.setStrokeColor(rule)
    pdf.line(left, 99, right, 99)
    notes = (
        "A record is one saved entry. Quantity is the number of units entered, including ammunition.",
        "An unrecorded serial number does not establish that an item has no serial number.",
        "Grouping: pistol/revolver -> Handgun; submachine gun -> Machine gun; unlisted types -> Other & custom.",
    )
    for index, note in enumerate(notes):
        text(note, left, 84 - index * 12, 7.5, color=muted, max_width=width)
    if data["photo_count"]:
        text(f"Photo records follow: {number(data['photo_count'])}. Each photo includes its operation and weapon details.",
             left, 48, 7.5, color=muted, max_width=width)
    text("InTrac | Operation summary", left, 32, 7.5, color=muted)
    if not data["photo_count"]:
        text("1 / 1", right, 32, 7.5, color=muted, align="right")
    pdf.showPage()
    pdf.save()
    return output.getvalue()
