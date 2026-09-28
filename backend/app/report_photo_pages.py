import io
from datetime import datetime, timezone
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from PIL import Image as PillowImage, ImageOps
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@lru_cache(maxsize=1)
def _fonts() -> tuple[str, str]:
    font_directory = Path("/usr/share/fonts/truetype/dejavu")
    if (font_directory / "DejaVuSans.ttf").exists():
        regular, bold = font_directory / "DejaVuSans.ttf", font_directory / "DejaVuSans-Bold.ttf"
    else:
        font_directory = Path(reportlab.__file__).parent / "fonts"
        regular, bold = font_directory / "Vera.ttf", font_directory / "VeraBd.ttf"
    pdfmetrics.registerFont(TTFont("InTracPhoto", str(regular)))
    pdfmetrics.registerFont(TTFont("InTracPhotoBold", str(bold)))
    pdfmetrics.registerFontFamily("InTracPhoto", normal="InTracPhoto", bold="InTracPhotoBold")
    return "InTracPhoto", "InTracPhotoBold"


def render_photo_pages(entry: dict, original: bytes) -> bytes:
    font, bold = _fonts()
    navy, teal, muted = (HexColor(value) for value in ("#183746", "#197765", "#58717D"))
    body = ParagraphStyle("PhotoBody", fontName=font, fontSize=10, leading=14, textColor=navy,
                          spaceAfter=4, splitLongWords=True)
    title = ParagraphStyle("PhotoTitle", parent=body, fontName=bold, fontSize=21, leading=26,
                           spaceAfter=5, keepWithNext=True)
    section = ParagraphStyle("PhotoSection", parent=body, fontName=bold, fontSize=10, textColor=teal,
                             spaceAfter=6, keepWithNext=True)
    label = ParagraphStyle("PhotoLabel", parent=body, fontSize=8, leading=11, textColor=muted,
                           spaceAfter=2, keepWithNext=True)
    subtitle = ParagraphStyle("PhotoSubtitle", parent=body, fontSize=9, textColor=muted, spaceAfter=16)
    log, weapon = entry["log"], entry["weapon"]

    def text(value):
        return escape("Not recorded" if value is None or value == "" else str(value)).replace("\n", "<br/>")

    def field(name, value):
        return [Paragraph(name, label), Paragraph(text(value), body)]

    def timestamp(value, date_only=False):
        if not value:
            return None
        pattern = "%d %b %Y" if date_only else "%d %b %Y, %H:%M UTC"
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime(pattern)

    def columns(left, right):
        table = Table(list(zip_longest(left, right, fillvalue="")), colWidths=[258, 258], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 20),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        return table

    def rule():
        return HRFlowable(width="100%", thickness=0.5, color=HexColor("#DCE5E8"), spaceAfter=12)

    preview_file = io.BytesIO()
    with PillowImage.open(io.BytesIO(original)) as source:
        preview = ImageOps.exif_transpose(source)
        preview.thumbnail((1584, 810), PillowImage.Resampling.LANCZOS)
        if "A" in preview.getbands() or "transparency" in preview.info:
            preview = preview.convert("RGBA")
            background = PillowImage.new("RGBA", preview.size, "white")
            background.alpha_composite(preview)
            preview = background.convert("RGB")
        else:
            preview = preview.convert("RGB")
        width, height = preview.size
        preview.save(preview_file, format="PNG")
    preview_file.seek(0)
    scale = min(516 / width, 260 / height)
    photo = Image(preview_file, width=width * scale, height=height * scale, hAlign="CENTER")

    location = log["location_name"]
    if not location and log["latitude"] is not None and log["longitude"] is not None:
        location = f"{log['latitude']:.6f}, {log['longitude']:.6f}"
    recorded_by = log["recorded_by"]
    operation_details = [Paragraph("Operation", section), field("Location", location)]
    if log["laf_soldier_name"]:
        operation_details.append(field("LAF Soldier Name", log["laf_soldier_name"]))
    operation_details.append(field("Recorded by", f"{recorded_by['first_name']} {recorded_by['last_name']}"))
    weapon_details = [Paragraph("Weapon", section), field("Weapon type", weapon["item_type"])]
    if weapon["name_model"]:
        weapon_details.append(field("Name/model", weapon["name_model"]))
    weapon_details.append(field("Quantity", weapon["quantity"]))
    status_color = "#197765" if log["status"] == "Verified" else "#58717D"
    story = [
        Paragraph(text(log["operation_name"]), title),
        Paragraph(f"{text(timestamp(log['occurred_at'], date_only=True))} &nbsp; | &nbsp; "
                  f'<font color="{status_color}"><b>{text(log["status"])}</b></font>', subtitle),
        photo,
        Spacer(1, 18),
        rule(),
        columns(operation_details, weapon_details),
        Spacer(1, 2),
        Paragraph("Serial numbers", section),
        *[Paragraph(text(serial), body) for serial in weapon["serial_numbers"] or ["Not recorded"]],
    ]
    if log["status"] == "Verified":
        story.extend([
            Spacer(1, 10), rule(),
            columns([field("Verified by", log["verified_by"])],
                    [field("Verified at", timestamp(log["verified_at"]))]),
        ])

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setFillColor(navy)
        canvas.setFont(bold, 9)
        canvas.drawString(48, 757, "PHOTO RECORD")
        canvas.setFillColor(muted)
        canvas.setFont(font, 8)
        canvas.drawRightString(564, 757, "InTrac")
        canvas.setStrokeColor(teal)
        canvas.line(48, 744, 564, 744)
        canvas.setFont(font, 7.5)
        canvas.drawString(48, 32, "Original photo and full metadata included as attachments.")
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, leftMargin=42, rightMargin=42,
                                 topMargin=60, bottomMargin=52, title="InTrac - Photo documentation")
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
