
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from time import perf_counter
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import getAscentDescent
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Flowable,
    KeepTogether,
    Paragraph,
    PageBreak,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

from app.models.database import (
    Asset,
    User,
    Relationship,
    Permission,
    Scenario,
    SimulationResult,
)

from app.services.attack_engine import analyze_scenario
from app.services.weakness_engine import analyze_weaknesses


logger = logging.getLogger(__name__)


# =========================================================
# REPORT THEME
# =========================================================

NAVY = colors.HexColor("#172536")
SLATE = colors.HexColor("#243B50")
SAGE = colors.HexColor("#8BBFB2")
MINT = colors.HexColor("#C5E2D9")
OFF_WHITE = colors.HexColor("#F2F6F4")
BORDER = colors.HexColor("#DCE6E2")
AMBER = colors.HexColor("#D69B65")

BLUE = SAGE
LIGHT_BLUE = OFF_WHITE
LIGHT_GREY = OFF_WHITE
MID_GREY = BORDER
DARK_GREY = SLATE

GREEN = SAGE
LIGHT_GREEN = colors.HexColor("#EAF3F0")

RED = colors.HexColor("#9B4D4D")
LIGHT_RED = colors.HexColor("#F7EEEE")

ORANGE = AMBER
LIGHT_ORANGE = colors.HexColor("#FAF3EB")

WHITE = colors.white


# =========================================================
# PAGE CONFIGURATION
# =========================================================

PAGE_WIDTH, PAGE_HEIGHT = A4

LEFT_MARGIN = 15 * mm
RIGHT_MARGIN = 15 * mm
TOP_MARGIN = 25 * mm
BOTTOM_MARGIN = 22 * mm

AVAILABLE_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN


def draw_brand_mark(canvas, x, y, size):
    """Draw the same Lucide Network mark used in the website sidebar."""

    canvas.saveState()
    canvas.setFillColor(SLATE)
    canvas.roundRect(x, y, size, size, size * 0.16, fill=1, stroke=0)

    icon_size = size * (23 / 42)
    scale = icon_size / 24
    offset_x = x + (size - icon_size) / 2
    offset_y = y + (size - icon_size) / 2

    def point(svg_x, svg_y):
        return offset_x + svg_x * scale, offset_y + (24 - svg_y) * scale

    canvas.setStrokeColor(MINT)
    canvas.setLineWidth(1.6 * scale)
    canvas.setLineCap(1)
    canvas.setLineJoin(1)

    for rect_x, rect_y in ((16, 16), (2, 16), (9, 2)):
        rect_width = 6 * scale
        rect_height = 6 * scale
        canvas.roundRect(
            offset_x + rect_x * scale,
            offset_y + (24 - rect_y - 6) * scale,
            rect_width,
            rect_height,
            scale,
            fill=0,
            stroke=1,
        )

    path = canvas.beginPath()
    path.moveTo(*point(5, 16))
    path.lineTo(*point(5, 13))
    path.curveTo(
        *point(5, 12.45),
        *point(5.45, 12),
        *point(6, 12),
    )
    path.lineTo(*point(18, 12))
    path.curveTo(
        *point(18.55, 12),
        *point(19, 12.45),
        *point(19, 13),
    )
    path.lineTo(*point(19, 16))
    canvas.drawPath(path, stroke=1, fill=0)

    path = canvas.beginPath()
    path.moveTo(*point(12, 12))
    path.lineTo(*point(12, 8))
    canvas.drawPath(path, stroke=1, fill=0)
    canvas.restoreState()


def draw_brand_lockup(
    canvas,
    x,
    y,
    mark_size,
    wordmark_size,
    tagline=False,
):
    canvas.saveState()
    mark_y = y + (12 if tagline else 0)
    draw_brand_mark(canvas, x, mark_y, mark_size)

    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", wordmark_size)
    ascent, descent = getAscentDescent(
        "Helvetica-Bold",
        wordmark_size,
    )
    center_y = mark_y + mark_size / 2
    baseline = center_y - (ascent + descent) / 2
    text_x = x + mark_size + 10
    canvas.drawString(text_x, baseline, "VULNWEAVE")

    if tagline:
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(
            text_x,
            y + 1.5,
            "ATTACK PATH INTELLIGENCE",
        )

    canvas.restoreState()


class BrandLockup(Flowable):
    def __init__(self, size=42):
        super().__init__()
        self.width = AVAILABLE_WIDTH
        self.height = size + 14
        self.size = size

    def draw(self):
        draw_brand_lockup(
            self.canv,
            0,
            0,
            self.size,
            17,
            tagline=True,
        )


# =========================================================
# GENERAL HELPERS
# =========================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError, OverflowError):
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default

        return int(value)

    except (TypeError, ValueError, OverflowError):
        return default


def format_number(value):
    number = safe_float(value)

    if number.is_integer():
        return str(int(number))

    return f"{number:.2f}"


def format_percentage(value):
    return f"{safe_float(value):.2f}%"


def safe_text(value, fallback="N/A"):
    if value is None:
        return fallback

    value = str(value).strip()

    return value if value else fallback


def paragraph_text(value):
    return escape(safe_text(value))


def make_paragraph(value, style):
    return Paragraph(
        paragraph_text(value),
        style,
    )


def get_first_value(data, keys, default=None):
    if not isinstance(data, dict):
        return default

    for key in keys:
        value = data.get(key)

        if value is not None:
            return value

    return default


def parse_relationship_ids(raw_value):
    """
    Safely parse relationship IDs stored as JSON.
    """

    try:
        parsed = json.loads(raw_value or "[]")

    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    result = []

    for item in parsed:
        if isinstance(item, bool):
            continue

        try:
            relationship_id = int(item)

            if relationship_id > 0 and relationship_id not in result:
                result.append(relationship_id)

        except (TypeError, ValueError, OverflowError):
            continue

    return result


# =========================================================
# PDF STYLES
# =========================================================

def create_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="VWTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=32,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=7,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=DARK_GREY,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWWordmark",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceAfter=3,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWCoverLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=SLATE,
            spaceAfter=7,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWMetaLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=SLATE,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWMetaValue",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=NAVY,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWSubheading",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=SLATE,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=DARK_GREY,
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=DARK_GREY,
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=DARK_GREY,
            wordWrap="CJK",
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWCellBold",
            parent=styles["VWCell"],
            fontName="Helvetica-Bold",
            textColor=NAVY,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWTableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=WHITE,
            alignment=TA_LEFT,
        )
    )

    styles.add(
        ParagraphStyle(
            name="VWCallout",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=NAVY,
        )
    )

    return styles


# =========================================================
# TABLE HELPERS
# =========================================================

def make_table(data, col_widths, header=True):
    """
    Create a consistently styled table with wrapped content.
    """

    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
        splitByRow=1,
        splitInRow=0,
    )

    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.35, MID_GREY),
    ]

    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ])

        if len(data) > 1:
            commands.append(
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [WHITE, LIGHT_GREY],
                )
            )

    table.setStyle(TableStyle(commands))

    return table


def add_callout(text, background=LIGHT_BLUE, styles=None):
    """
    Create a highlighted information section.

    The supplied text is trusted report markup.
    Dynamic values must be escaped before being inserted.
    """

    if styles is None:
        styles = create_styles()

    paragraph = Paragraph(
        text,
        styles["VWCallout"],
    )

    table = Table(
        [[paragraph]],
        colWidths=[AVAILABLE_WIDTH],
    )

    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), background),
            ("BOX", (0, 0), (-1, -1), 0.6, MID_GREY),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    return table


# =========================================================
# PAGE HEADER AND FOOTER
# =========================================================

class NumberedCanvas(pdf_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for page_number, page_state in enumerate(
            self._saved_page_states,
            start=1,
        ):
            self.__dict__.update(page_state)
            self.saveState()
            self.setFont("Helvetica", 7)
            self.setFillColor(DARK_GREY)
            self.drawRightString(
                PAGE_WIDTH - RIGHT_MARGIN,
                11 * mm,
                f"Page {page_number} of {page_count}",
            )
            self.restoreState()
            super().showPage()

        super().save()


def draw_page(canvas, document):
    """
    Draw header, footer and page number on every page.
    """

    canvas.saveState()

    page_width, page_height = A4

    draw_brand_lockup(
        canvas,
        LEFT_MARGIN,
        page_height - 15.6 * mm,
        12,
        8,
    )

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(DARK_GREY)
    canvas.drawRightString(
        page_width - RIGHT_MARGIN,
        page_height - 12.5 * mm,
        "SECURITY ASSESSMENT REPORT",
    )

    canvas.setStrokeColor(MID_GREY)
    canvas.setLineWidth(0.5)

    canvas.line(
        LEFT_MARGIN,
        page_height - 16 * mm,
        page_width - RIGHT_MARGIN,
        page_height - 16 * mm,
    )

    # Footer
    canvas.line(
        LEFT_MARGIN,
        17 * mm,
        page_width - RIGHT_MARGIN,
        17 * mm,
    )

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(DARK_GREY)

    canvas.drawString(
        LEFT_MARGIN,
        11 * mm,
        "VulnWeave | Security Assessment Report",
    )

    canvas.restoreState()


# =========================================================
# ASSET AND RELATIONSHIP HELPERS
# =========================================================

def resolve_endpoint_name(
    db,
    endpoint_type,
    endpoint_id,
    endpoint_names=None,
):
    """
    Resolve a relationship endpoint to its display name.
    """

    if endpoint_names is not None:
        name = endpoint_names.get((endpoint_type, endpoint_id))
        if name is not None:
            return name

    if endpoint_type == "asset":
        item = db.query(Asset).filter(
            Asset.id == endpoint_id
        ).first()

        if item:
            return item.name

    elif endpoint_type == "user":
        item = db.query(User).filter(
            User.id == endpoint_id
        ).first()

        if item:
            return (
                getattr(item, "username", None)
                or getattr(item, "email", None)
                or f"User {endpoint_id}"
            )

    return f"{safe_text(endpoint_type, 'Unknown').title()} {endpoint_id}"


def get_relationship_details(
    db,
    relationship,
    endpoint_names=None,
    permissions=None,
):
    """
    Return readable relationship information.
    """

    source_name = resolve_endpoint_name(
        db,
        relationship.source_type,
        relationship.source_id,
        endpoint_names,
    )

    target_name = resolve_endpoint_name(
        db,
        relationship.target_type,
        relationship.target_id,
        endpoint_names,
    )

    permission = None

    if relationship.permission_id is not None:
        if permissions is not None:
            permission = permissions.get(relationship.permission_id)
        else:
            permission = db.query(Permission).filter(
                Permission.id == relationship.permission_id
            ).first()

    permission_name = (
        permission.name
        if permission
        else "Unspecified"
    )

    return {
        "id": relationship.id,
        "source": source_name,
        "target": target_name,
        "permission": permission_name,
        "description": relationship.description or "",
    }


def load_report_context(db):
    users = db.query(User).filter(User.is_active == True).all()
    assets = db.query(Asset).filter(Asset.is_active == True).all()
    relationships = db.query(Relationship).all()

    asset_ids = {
        asset.id
        for asset in assets
    }
    user_ids = {
        user.id
        for user in users
    }
    permission_ids = set()

    for relationship in relationships:
        if relationship.source_type == "asset":
            asset_ids.add(relationship.source_id)
        elif relationship.source_type == "user":
            user_ids.add(relationship.source_id)

        if relationship.target_type == "asset":
            asset_ids.add(relationship.target_id)
        elif relationship.target_type == "user":
            user_ids.add(relationship.target_id)

        if relationship.permission_id is not None:
            permission_ids.add(relationship.permission_id)

    endpoint_names = {}
    weakness_endpoint_names = {}

    if asset_ids:
        for asset in db.query(Asset).filter(Asset.id.in_(asset_ids)).all():
            endpoint_names[("asset", asset.id)] = asset.name
            weakness_endpoint_names[("asset", asset.id)] = asset.name

    if user_ids:
        for user in db.query(User).filter(User.id.in_(user_ids)).all():
            endpoint_names[("user", user.id)] = (
                user.username
                or user.email
                or f"User {user.id}"
            )
            weakness_endpoint_names[("user", user.id)] = getattr(
                user,
                "username",
                f"User {user.id}",
            )

    permissions = {}
    if permission_ids:
        permissions = {
            permission.id: permission
            for permission in db.query(Permission).filter(
                Permission.id.in_(permission_ids)
            ).all()
        }

    return {
        "users": users,
        "assets": assets,
        "relationships": relationships,
        "endpoint_names": endpoint_names,
        "weakness_endpoint_names": weakness_endpoint_names,
        "permissions": permissions,
    }


# =========================================================
# BASELINE ATTACK PATH SECTION
# =========================================================

def add_attack_path_section(story, styles, analysis):
    story.append(
        Paragraph(
            "Baseline Attack Path Analysis",
            styles["VWHeading"],
        )
    )

    paths = analysis.get("paths") or []

    if not paths:
        story.append(
            Paragraph(
                "No reachable attack paths were identified in the "
                "current scenario analysis.",
                styles["VWBody"],
            )
        )
        return

    story.append(
        Paragraph(
            f"Total reachable attack paths: <b>{len(paths)}</b>",
            styles["VWBody"],
        )
    )

    rows = [[
        Paragraph("Attack Path", styles["VWTableHeader"]),
        Paragraph("Risk Score", styles["VWTableHeader"]),
        Paragraph("Target Sensitivity", styles["VWTableHeader"]),
    ]]

    for path in paths:
        labels = path.get("labels") or path.get("nodes") or []

        route = " → ".join(
            safe_text(label, "Unknown")
            for label in labels
        )

        rows.append([
            make_paragraph(route, styles["VWCell"]),
            make_paragraph(
                format_number(path.get("risk_score", 0)),
                styles["VWCell"],
            ),
            make_paragraph(
                path.get("target_sensitivity", "N/A"),
                styles["VWCell"],
            ),
        ])

    widths = [
        AVAILABLE_WIDTH * 0.66,
        AVAILABLE_WIDTH * 0.15,
        AVAILABLE_WIDTH * 0.19,
    ]

    story.append(
        make_table(rows, widths)
    )


# =========================================================
# WEAKNESS ASSESSMENT SECTION
# =========================================================

def add_weakness_section(story, styles, weakness_report):
    heading = Paragraph(
        "Relationship Weakness Assessment",
        styles["VWHeading"],
    )

    findings = weakness_report.get("findings") or []

    if not findings:
        story.append(heading)
        story.append(
            Paragraph(
                "No relationship weakness findings were returned.",
                styles["VWBody"],
            )
        )
        return

    explanation = Paragraph(
        "These findings represent the simulated impact of removing "
        "individual relationships from the attack graph. "
        "They are not CVSS vulnerability scores.",
        styles["VWSmall"],
    )

    rows = [[
        Paragraph("Relationship", styles["VWTableHeader"]),
        Paragraph("Blocked", styles["VWTableHeader"]),
        Paragraph("Risk Reduction", styles["VWTableHeader"]),
        Paragraph("Reduction %", styles["VWTableHeader"]),
        Paragraph("Priority Score", styles["VWTableHeader"]),
        Paragraph("Priority", styles["VWTableHeader"]),
    ]]

    for finding in findings:
        relationship_name = get_first_value(
            finding,
            ["relationship_name", "relationship"],
        )

        if not relationship_name:
            source = get_first_value(
                finding,
                ["source_name", "source"],
                "Unknown",
            )

            target = get_first_value(
                finding,
                ["target_name", "target"],
                "Unknown",
            )

            relationship_name = f"{source} → {target}"

        blocked = get_first_value(
            finding,
            ["blocked_paths", "paths_blocked"],
            0,
        )

        risk_reduction = get_first_value(
            finding,
            ["risk_reduction", "risk_reduction_score"],
            0,
        )

        reduction_percent = get_first_value(
            finding,
            ["risk_reduction_percent", "reduction_percent"],
            0,
        )

        priority_score = get_first_value(
            finding,
            ["priority_score", "impact_score"],
            0,
        )

        priority = get_first_value(
            finding,
            ["priority", "priority_level"],
            "N/A",
        )

        rows.append([
            make_paragraph(relationship_name, styles["VWCell"]),
            make_paragraph(
                str(safe_int(blocked)),
                styles["VWCell"],
            ),
            make_paragraph(
                format_number(risk_reduction),
                styles["VWCell"],
            ),
            make_paragraph(
                format_percentage(reduction_percent),
                styles["VWCell"],
            ),
            make_paragraph(
                format_number(priority_score),
                styles["VWCell"],
            ),
            make_paragraph(
                priority,
                styles["VWCell"],
            ),
        ])

    widths = [
        AVAILABLE_WIDTH * 0.31,
        AVAILABLE_WIDTH * 0.09,
        AVAILABLE_WIDTH * 0.13,
        AVAILABLE_WIDTH * 0.12,
        AVAILABLE_WIDTH * 0.17,
        AVAILABLE_WIDTH * 0.18,
    ]

    weakness_table = make_table(rows, widths)
    story.append(
        KeepTogether([
            heading,
            explanation,
            weakness_table,
        ])
    )


# =========================================================
# DEFENSIVE RECOMMENDATIONS
# =========================================================

def add_recommendations(story, styles, weakness_report):
    story.append(
        Paragraph(
            "Defensive Recommendations",
            styles["VWHeading"],
        )
    )

    findings = weakness_report.get("findings") or []

    if not findings:
        story.append(
            Paragraph(
                "Review the environment periodically and maintain "
                "appropriate access controls.",
                styles["VWBody"],
            )
        )
        return

    recommendation_rows = [[
        Paragraph("Priority", styles["VWTableHeader"]),
        Paragraph("Relationship", styles["VWTableHeader"]),
        Paragraph("Expected Impact", styles["VWTableHeader"]),
        Paragraph("Remediation Guidance", styles["VWTableHeader"]),
    ]]

    for finding in findings:
        priority = str(
            get_first_value(
                finding,
                ["priority", "priority_level"],
                "N/A",
            )
        )
        source = get_first_value(
            finding,
            ["source_name", "source"],
            "Unknown",
        )
        target = get_first_value(
            finding,
            ["target_name", "target"],
            "Unknown",
        )
        relationship_name = get_first_value(
            finding,
            ["relationship_name", "relationship"],
            f"{source} → {target}",
        )
        blocked = safe_int(
            get_first_value(
                finding,
                ["blocked_paths", "paths_blocked"],
                0,
            )
        )
        risk_reduction = format_number(
            get_first_value(
                finding,
                ["risk_reduction", "risk_reduction_score"],
                0,
            )
        )
        reduction_percent = format_percentage(
            get_first_value(
                finding,
                ["risk_reduction_percent", "reduction_percent"],
                0,
            )
        )

        if priority.lower() == "high":
            remediation = (
                "Validate the business need; if not essential, restrict "
                "the relationship to least privilege and rerun the analysis."
            )
        elif priority.lower() == "medium":
            remediation = (
                "Review alternate access routes and narrow permissions "
                "to the minimum required."
            )
        else:
            remediation = (
                "Retain only if required and include it in periodic "
                "access reviews."
            )

        recommendation_rows.append([
            make_paragraph(priority, styles["VWCell"]),
            make_paragraph(relationship_name, styles["VWCell"]),
            make_paragraph(
                f"{blocked} path(s) blocked; {risk_reduction} risk "
                f"reduction ({reduction_percent}) in the removal "
                "simulation.",
                styles["VWCell"],
            ),
            make_paragraph(remediation, styles["VWCell"]),
        ])

    story.append(
        make_table(
            recommendation_rows,
            [
                AVAILABLE_WIDTH * 0.12,
                AVAILABLE_WIDTH * 0.24,
                AVAILABLE_WIDTH * 0.27,
                AVAILABLE_WIDTH * 0.37,
            ],
        )
    )

    story.append(Spacer(1, 6))

    high_findings = [
        finding
        for finding in findings
        if str(
            get_first_value(
                finding,
                ["priority", "priority_level"],
                "",
            )
        ).lower() == "high"
    ]

    medium_findings = [
        finding
        for finding in findings
        if str(
            get_first_value(
                finding,
                ["priority", "priority_level"],
                "",
            )
        ).lower() == "medium"
    ]

    if high_findings:
        story.append(
            Paragraph(
                "<b>High priority:</b> Review relationships with the "
                "greatest simulated attack-path and risk reduction. "
                "Apply least-privilege access and remove unnecessary "
                "administrative permissions where appropriate.",
                styles["VWBody"],
            )
        )

    if medium_findings:
        story.append(
            Paragraph(
                "<b>Medium priority:</b> Review alternative access routes "
                "and reduce unnecessary connections between accounts, "
                "servers and sensitive assets.",
                styles["VWBody"],
            )
        )

    story.append(
        Paragraph(
            "<b>General recommendation:</b> Reassess the attack graph "
            "after each access-control change and verify that critical "
            "assets remain appropriately protected.",
            styles["VWBody"],
        )
    )


# =========================================================
# SIMULATION REPORT SECTION
# =========================================================

def add_simulation_section(
    db,
    story,
    styles,
    scenario_id,
    simulation,
    scenario=None,
    graph_data=None,
):
    simulation_intro = [
        Paragraph(
            "Defensive Simulation Analysis",
            styles["VWHeading"],
        )
    ]

    selected_ids = parse_relationship_ids(
        simulation.selected_relationship_ids
    )

    before_paths = safe_int(
        simulation.before_path_count
    )

    after_paths = safe_int(
        simulation.after_path_count
    )

    blocked_paths = safe_int(
        simulation.blocked_paths
    )

    before_risk = safe_float(
        simulation.before_risk_total
    )

    after_risk = safe_float(
        simulation.after_risk_total
    )

    risk_reduction = max(
        0,
        before_risk - after_risk,
    )

    risk_reduction_percent = (
        risk_reduction / before_risk * 100
        if before_risk > 0
        else 0
    )

    simulation_intro.append(
        Paragraph(
            f"<b>Simulation ID:</b> {safe_int(simulation.id)}",
            styles["VWBody"],
        )
    )

    if simulation.created_at:
        created_at = simulation.created_at

        if created_at.tzinfo is None:
            created_at = created_at.replace(
                tzinfo=timezone.utc
            )

        simulation_intro.append(
            Paragraph(
                f"<b>Saved on:</b> "
                f"{created_at.strftime('%d %B %Y, %H:%M UTC')}",
                styles["VWBody"],
            )
        )

    # -----------------------------------------------------
    # Before and after comparison
    # -----------------------------------------------------

    comparison_rows = [
        [
            Paragraph("Metric", styles["VWTableHeader"]),
            Paragraph("Before", styles["VWTableHeader"]),
            Paragraph("After", styles["VWTableHeader"]),
            Paragraph("Change", styles["VWTableHeader"]),
        ],
        [
            make_paragraph(
                "Reachable attack paths",
                styles["VWCellBold"],
            ),
            make_paragraph(
                str(before_paths),
                styles["VWCell"],
            ),
            make_paragraph(
                str(after_paths),
                styles["VWCell"],
            ),
            make_paragraph(
                f"{blocked_paths} blocked",
                styles["VWCell"],
            ),
        ],
        [
            make_paragraph(
                "Aggregate risk score",
                styles["VWCellBold"],
            ),
            make_paragraph(
                format_number(before_risk),
                styles["VWCell"],
            ),
            make_paragraph(
                format_number(after_risk),
                styles["VWCell"],
            ),
            make_paragraph(
                f"{format_number(risk_reduction)} reduced",
                styles["VWCell"],
            ),
        ],
    ]

    comparison_widths = [
        AVAILABLE_WIDTH * 0.36,
        AVAILABLE_WIDTH * 0.19,
        AVAILABLE_WIDTH * 0.19,
        AVAILABLE_WIDTH * 0.26,
    ]

    simulation_intro.append(
        make_table(
            comparison_rows,
            comparison_widths,
        )
    )
    story.append(KeepTogether(simulation_intro))

    story.append(Spacer(1, 7))

    story.append(
        add_callout(
            "<b>Overall simulated risk reduction: "
            f"{format_percentage(risk_reduction_percent)}</b>",
            LIGHT_GREEN if risk_reduction > 0 else LIGHT_ORANGE,
            styles,
        )
    )

    # -----------------------------------------------------
    # Restricted relationships
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Restricted Relationships",
            styles["VWSubheading"],
        )
    )

    if not selected_ids:
        story.append(
            Paragraph(
                "No relationship IDs were recorded for this simulation.",
                styles["VWBody"],
            )
        )

    else:
        relationships = (
            graph_data["relationships"]
            if graph_data is not None
            else db.query(Relationship).filter(
                Relationship.id.in_(selected_ids)
            ).all()
        )
        selected_relationships = {
            relationship.id: relationship
            for relationship in relationships
            if relationship.id in selected_ids
        }

        relationship_rows = [[
            Paragraph("ID", styles["VWTableHeader"]),
            Paragraph("Source", styles["VWTableHeader"]),
            Paragraph("Target", styles["VWTableHeader"]),
            Paragraph("Permission", styles["VWTableHeader"]),
        ]]

        for relationship_id in selected_ids:
            relationship = selected_relationships.get(
                relationship_id
            )

            if relationship:
                details = get_relationship_details(
                    db,
                    relationship,
                    endpoint_names=(
                        graph_data.get("endpoint_names")
                        if graph_data is not None
                        else None
                    ),
                    permissions=(
                        graph_data.get("permissions")
                        if graph_data is not None
                        else None
                    ),
                )

                relationship_rows.append([
                    make_paragraph(
                        str(relationship_id),
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        details["source"],
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        details["target"],
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        details["permission"],
                        styles["VWCell"],
                    ),
                ])

            else:
                relationship_rows.append([
                    make_paragraph(
                        str(relationship_id),
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        "Unavailable",
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        "Unavailable",
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        "Relationship no longer exists",
                        styles["VWCell"],
                    ),
                ])

        relationship_widths = [
            AVAILABLE_WIDTH * 0.10,
            AVAILABLE_WIDTH * 0.31,
            AVAILABLE_WIDTH * 0.31,
            AVAILABLE_WIDTH * 0.28,
        ]

        story.append(
            make_table(
                relationship_rows,
                relationship_widths,
            )
        )

    # -----------------------------------------------------
    # Remaining attack paths
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Remaining Attack Paths",
            styles["VWSubheading"],
        )
    )

    try:
        reconstructed = analyze_scenario(
            db,
            scenario_id,
            removed_relationship_ids=selected_ids,
            save_results=False,
            scenario=scenario,
            graph_data=graph_data,
        )

        remaining_paths = reconstructed.get("paths") or []

        if not remaining_paths:
            story.append(
                Paragraph(
                    "No remaining reachable attack paths were found "
                    "in the reconstructed current environment.",
                    styles["VWBody"],
                )
            )

        else:
            remaining_rows = [[
                Paragraph("Remaining Path", styles["VWTableHeader"]),
                Paragraph("Risk Score", styles["VWTableHeader"]),
                Paragraph("Target Sensitivity", styles["VWTableHeader"]),
            ]]

            for path in remaining_paths:
                labels = path.get("labels") or path.get("nodes") or []

                route = " → ".join(
                    safe_text(label, "Unknown")
                    for label in labels
                )

                remaining_rows.append([
                    make_paragraph(
                        route,
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        format_number(path.get("risk_score", 0)),
                        styles["VWCell"],
                    ),
                    make_paragraph(
                        path.get("target_sensitivity", "N/A"),
                        styles["VWCell"],
                    ),
                ])

            remaining_widths = [
                AVAILABLE_WIDTH * 0.66,
                AVAILABLE_WIDTH * 0.15,
                AVAILABLE_WIDTH * 0.19,
            ]

            story.append(
                make_table(
                    remaining_rows,
                    remaining_widths,
                )
            )

    except Exception:
        story.append(
            Paragraph(
                "Remaining paths could not be reconstructed from the "
                "current environment. The saved simulation metrics "
                "above remain unchanged.",
                styles["VWBody"],
            )
        )

    story.append(Spacer(1, 7))

    story.append(
        add_callout(
            "<b>Historical data limitation:</b> The before/after metrics "
            "and selected relationship IDs above are read from the saved "
            "simulation record. Remaining attack paths and relationship "
            "names are reconstructed using the current database state. "
            "They may differ from the exact environment at the time the "
            "simulation was originally run.",
            LIGHT_ORANGE,
            styles,
        )
    )


# =========================================================
# METHODOLOGY AND LIMITATIONS
# =========================================================

def add_methodology(
    story,
    styles,
    analysis,
    weakness_report,
    graph_data,
):
    story.append(
        Paragraph(
            "Assessment Scope and Methodology",
            styles["VWHeading"],
        )
    )

    active_assets = graph_data["assets"]
    asset_names = ", ".join(
        safe_text(asset.name, "Unnamed asset")
        for asset in active_assets
    ) or "No active assets returned"

    scope_details = [
        (
            "Entry asset",
            safe_text(analysis.get("entry_asset")),
        ),
        (
            f"Active assets ({len(active_assets)})",
            asset_names,
        ),
        (
            "Relationships reviewed",
            str(safe_int(
                weakness_report.get(
                    "total_relationships_reviewed",
                    0,
                )
            )),
        ),
    ]

    for label, value in scope_details:
        story.append(
            Paragraph(
                f"<b>{escape(label)}:</b> {paragraph_text(value)}",
                styles["VWBody"],
            )
        )

    methodology = [
        (
            "Attack path analysis",
            "A directed graph is constructed from the active users, "
            "assets and relationships in the scenario. Reachable paths "
            "to high- and critical-sensitivity assets are evaluated."
        ),
        (
            "Risk scoring",
            "Risk scores are heuristic estimates based on asset "
            "sensitivity and path characteristics. They are intended "
            "for comparative analysis within this demonstration system."
        ),
        (
            "Weakness prioritization",
            "Relationship priority scores represent the simulated impact "
            "of removing individual relationships. They are not CVSS "
            "scores."
        ),
        (
            "Simulation",
            "A defensive simulation removes selected relationships "
            "from a temporary analysis graph. It does not modify the "
            "original scenario relationships."
        ),
        (
            "Scope",
            "This report describes the configured VulnWeave demonstration "
            "environment. Results depend on the accuracy and completeness "
            "of the supplied assets and relationships."
        ),
    ]

    for heading, description in methodology:
        story.append(
            Paragraph(
                f"<b>{escape(heading)}:</b> {escape(description)}",
                styles["VWBody"],
            )
        )


def add_limitations(story, styles):
    story.append(
        Paragraph(
            "Limitations and Disclaimer",
            styles["VWHeading"],
        )
    )

    limitations = [
        "Risk scores are heuristic estimates and are not CVSS scores.",
        "Identified paths and relationship impacts do not prove "
        "exploitability or confirm the presence of a vulnerability.",
        "Results are limited to the configured VulnWeave demonstration "
        "environment and the accuracy and completeness of its supplied "
        "assets and relationships.",
    ]

    for limitation in limitations:
        story.append(
            Paragraph(
                f"• {escape(limitation)}",
                styles["VWBody"],
            )
        )


# =========================================================
# MAIN REPORT GENERATOR
# =========================================================

def generate_security_report(
    db,
    scenario_id,
    simulation_id=None,
    *,
    scenario_record=None,
    simulation_record=None,
):
    """
    Generate a portrait A4 security assessment PDF.

    Without simulation_id:
        Generate the baseline security report.

    With simulation_id:
        Generate the baseline report plus the selected saved
        defensive simulation analysis.
    """

    total_started = perf_counter()
    lookup_started = total_started

    scenario = scenario_record
    if scenario is None:
        scenario = db.query(Scenario).filter(
            Scenario.id == scenario_id
        ).first()
    elif scenario.id != scenario_id:
        raise ValueError("Scenario record does not match scenario ID.")

    if not scenario:
        raise ValueError("Scenario not found.")

    simulation = simulation_record
    if simulation_id is not None:
        if simulation is None:
            simulation = db.query(SimulationResult).filter(
                SimulationResult.id == simulation_id,
                SimulationResult.scenario_id == scenario_id,
            ).first()
        elif (
            simulation.id != simulation_id
            or simulation.scenario_id != scenario_id
        ):
            raise ValueError(
                "Simulation record does not match the requested scenario."
            )

        if not simulation:
            raise ValueError(
                "Simulation not found for the selected scenario."
            )
    elif simulation is not None:
        raise ValueError("A simulation record requires a simulation ID.")

    lookup_seconds = perf_counter() - lookup_started

    context_started = perf_counter()
    graph_data = load_report_context(db)
    context_seconds = perf_counter() - context_started

    analysis_started = perf_counter()
    analysis = analyze_scenario(
        db,
        scenario_id,
        save_results=False,
        scenario=scenario,
        graph_data=graph_data,
    )
    analysis_seconds = perf_counter() - analysis_started

    weakness_started = perf_counter()
    weakness_report = analyze_weaknesses(
        db,
        scenario_id,
        scenario=scenario,
        baseline_analysis=analysis,
        graph_data=graph_data,
    )
    weakness_seconds = perf_counter() - weakness_started

    total_paths = safe_int(
        analysis.get(
            "total_paths",
            len(analysis.get("paths") or []),
        )
    )
    total_relationships = safe_int(
        weakness_report.get(
            "total_relationships_reviewed",
            0,
        )
    )
    baseline_risk_total = sum(
        safe_float(path.get("risk_score", 0))
        for path in (analysis.get("paths") or [])
    )

    generated_at_datetime = datetime.now(timezone.utc)
    generated_at = generated_at_datetime.strftime(
        "%d %B %Y, %H:%M UTC"
    )
    report_id = (
        f"VW-SA-{safe_int(scenario_id):04d}-"
        f"{generated_at_datetime:%Y%m%d}"
    )
    if simulation is not None:
        report_id = f"{report_id}-SIM-{safe_int(simulation.id):04d}"

    render_started = perf_counter()
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=RIGHT_MARGIN,
        leftMargin=LEFT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"VulnWeave Security Report - {scenario.name}",
        author="VulnWeave",
        subject="Attack Path Analysis and Defensive Optimization",
    )

    styles = create_styles()
    story = []

    story.append(Spacer(1, 23 * mm))
    story.append(BrandLockup(42))
    story.append(Spacer(1, 18 * mm))

    story.append(
        Paragraph(
            "SECURITY ENGINEERING / ASSESSMENT",
            styles["VWCoverLabel"],
        )
    )
    story.append(
        Paragraph(
            "Attack Path Analysis<br/>and Defensive Optimization",
            styles["VWTitle"],
        )
    )
    story.append(
        Paragraph(
            "Security Assessment Report",
            styles["VWSubtitle"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=SAGE,
            spaceBefore=4,
            spaceAfter=12,
        )
    )

    report_type = (
        f"Simulation Assessment #{simulation.id}"
        if simulation
        else "Security Assessment Report"
    )

    cover_rows = [
        ("Report type", report_type),
        ("Scenario", safe_text(scenario.name)),
        ("Scenario ID", str(safe_int(scenario_id))),
    ]
    if simulation is not None:
        cover_rows.append(
            ("Simulation ID", str(safe_int(simulation.id)))
        )
    cover_rows.extend([
        ("Report ID", report_id),
        ("Generated", generated_at),
    ])

    cover_table = Table(
        [
            [
                make_paragraph(label, styles["VWMetaLabel"]),
                make_paragraph(value, styles["VWMetaValue"]),
            ]
            for label, value in cover_rows
        ],
        colWidths=[
            AVAILABLE_WIDTH * 0.26,
            AVAILABLE_WIDTH * 0.74,
        ],
        hAlign="LEFT",
    )
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), OFF_WHITE),
        ("BACKGROUND", (1, 0), (1, -1), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.4, MID_GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            "ASSESSMENT AT A GLANCE",
            styles["VWCoverLabel"],
        )
    )

    cover_metrics = Table(
        [
            [
                make_paragraph("Baseline Paths", styles["VWMetaLabel"]),
                make_paragraph(
                    "Relationships Reviewed",
                    styles["VWMetaLabel"],
                ),
                make_paragraph("Baseline Risk", styles["VWMetaLabel"]),
            ],
            [
                make_paragraph(str(total_paths), styles["VWWordmark"]),
                make_paragraph(
                    str(total_relationships),
                    styles["VWWordmark"],
                ),
                make_paragraph(
                    format_number(baseline_risk_total),
                    styles["VWWordmark"],
                ),
            ],
        ],
        colWidths=[AVAILABLE_WIDTH / 3] * 3,
        hAlign="LEFT",
    )
    cover_metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OFF_WHITE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, MID_GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(cover_metrics)
    story.append(Spacer(1, 7 * mm))
    story.append(
        Paragraph(
            "Generated by the VulnWeave security assessment platform.",
            styles["VWSmall"],
        )
    )
    story.append(PageBreak())

    # -----------------------------------------------------
    # Executive summary
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Executive Summary",
            styles["VWHeading"],
        )
    )

    summary_rows = [
        [
            make_paragraph(
                "Baseline Paths",
                styles["VWTableHeader"],
            ),
            make_paragraph(
                "Relationships Reviewed",
                styles["VWTableHeader"],
            ),
            make_paragraph(
                "Baseline Risk",
                styles["VWTableHeader"],
            ),
            make_paragraph(
                "Scenario",
                styles["VWTableHeader"],
            ),
        ],
        [
            make_paragraph(
                str(total_paths),
                styles["VWCell"],
            ),
            make_paragraph(
                str(total_relationships),
                styles["VWCell"],
            ),
            make_paragraph(
                format_number(baseline_risk_total),
                styles["VWCell"],
            ),
            make_paragraph(
                scenario.name,
                styles["VWCell"],
            ),
        ],
    ]

    summary_widths = [
        AVAILABLE_WIDTH * 0.20,
        AVAILABLE_WIDTH * 0.25,
        AVAILABLE_WIDTH * 0.18,
        AVAILABLE_WIDTH * 0.37,
    ]

    story.append(
        make_table(
            summary_rows,
            summary_widths,
        )
    )

    story.append(Spacer(1, 8))

    if total_paths:
        assessment_summary = (
            f"The current scenario analysis identified {total_paths} "
            f"reachable attack path(s), with an aggregate heuristic risk "
            f"score of {format_number(baseline_risk_total)}. "
            f"The assessment reviewed {total_relationships} "
            "relationships."
        )
    else:
        assessment_summary = (
            "The current scenario analysis identified no reachable "
            "attack paths. The assessment reviewed "
            f"{total_relationships} relationships."
        )

    story.append(
        Paragraph(
            escape(assessment_summary),
            styles["VWBody"],
        )
    )

    story.append(
        Paragraph(
            "Key Findings",
            styles["VWSubheading"],
        )
    )

    key_findings = []
    paths = analysis.get("paths") or []
    if paths:
        highest_risk_path = paths[0]
        labels = highest_risk_path.get("labels") or []
        route = " → ".join(
            safe_text(label, "Unknown")
            for label in labels
        )
        key_findings.append(
            "Highest-risk reachable path: "
            f"{route} (risk {format_number(highest_risk_path.get('risk_score', 0))})."
        )
    else:
        key_findings.append("No reachable attack paths were identified.")

    findings = weakness_report.get("findings") or []
    if findings:
        finding = findings[0]
        source = safe_text(
            get_first_value(finding, ["source_name", "source"], "Unknown")
        )
        target = safe_text(
            get_first_value(finding, ["target_name", "target"], "Unknown")
        )
        blocked = safe_int(
            get_first_value(finding, ["blocked_paths", "paths_blocked"], 0)
        )
        risk_reduction = format_number(
            get_first_value(
                finding,
                ["risk_reduction", "risk_reduction_score"],
                0,
            )
        )
        priority = safe_text(
            get_first_value(
                finding,
                ["priority", "priority_level"],
                "N/A",
            )
        )
        key_findings.append(
            "Most impactful single-relationship removal: "
            f"{source} → {target} (priority {priority}; "
            f"{blocked} path(s) blocked; risk reduction {risk_reduction})."
        )
    else:
        key_findings.append(
            "No relationship weakness findings were returned."
        )

    for key_finding in key_findings:
        story.append(
            Paragraph(
                f"• {escape(key_finding)}",
                styles["VWSmall"],
            )
        )

    if simulation:
        story.append(
            add_callout(
                "This document includes the baseline security assessment "
                "and the selected saved defensive simulation.",
                LIGHT_GREEN,
                styles,
            )
        )
    else:
        story.append(
            add_callout(
                "This document presents the baseline security assessment "
                "for the selected scenario.",
                LIGHT_BLUE,
                styles,
            )
        )

    # -----------------------------------------------------
    # Scope and methodology
    # -----------------------------------------------------

    add_methodology(
        story,
        styles,
        analysis,
        weakness_report,
        graph_data,
    )

    # -----------------------------------------------------
    # Baseline report sections
    # -----------------------------------------------------

    add_attack_path_section(
        story,
        styles,
        analysis,
    )

    add_weakness_section(
        story,
        styles,
        weakness_report,
    )

    add_recommendations(
        story,
        styles,
        weakness_report,
    )

    # -----------------------------------------------------
    # Optional simulation report section
    # -----------------------------------------------------

    if simulation is not None:
        add_simulation_section(
            db,
            story,
            styles,
            scenario_id,
            simulation,
            scenario=scenario,
            graph_data=graph_data,
        )

    # -----------------------------------------------------
    # Limitations
    # -----------------------------------------------------

    add_limitations(
        story,
        styles,
    )

    # -----------------------------------------------------
    # Build PDF
    # -----------------------------------------------------

    document.build(
        story,
        onFirstPage=draw_page,
        onLaterPages=draw_page,
        canvasmaker=NumberedCanvas,
    )

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        "Security report generated scenario_id=%s simulation_id=%s "
        "lookup_seconds=%.3f context_seconds=%.3f "
        "attack_analysis_seconds=%.3f weakness_analysis_seconds=%.3f "
        "pdf_render_seconds=%.3f total_seconds=%.3f",
        scenario_id,
        simulation_id,
        lookup_seconds,
        context_seconds,
        analysis_seconds,
        weakness_seconds,
        perf_counter() - render_started,
        perf_counter() - total_started,
    )

    return pdf_bytes
