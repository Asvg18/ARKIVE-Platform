"""Renders the interview results report as a printable PDF."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.interview_report import InterviewReport, InterviewReportCell

__all__ = ["render_interview_report_pdf"]

_LOGO = Path(__file__).resolve().parent.parent / "assets" / "arkive-logo.png"

# the app's own tokens (frontend/src/styles/tokens.css), so the paper
# reads as the same product as the screen
INK_900 = colors.HexColor("#1c1c1f")
INK_700 = colors.HexColor("#404047")
INK_600 = colors.HexColor("#5e5e67")
INK_400 = colors.HexColor("#97979f")
RULE = colors.HexColor("#dcdce1")
WELL = colors.HexColor("#f1f1f4")
ACCENT = colors.HexColor("#cf2814")  # the brand red, as --accent in tokens.css
SUCCESS = colors.HexColor("#067a55")
DANGER = colors.HexColor("#b42318")

_RECOMMENDATION_COLOUR = {
    "highly_recommended": SUCCESS,
    "recommended": INK_700,
    "not_recommended": DANGER,
}

MARGIN = 0.6 * inch
FONT = "Helvetica"
BOLD = "Helvetica-Bold"


def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName=FONT, fontSize=9, leading=12, textColor=INK_900)
    return ParagraphStyle(name, **{**base, **kw})


S_BRAND = _style("brand", fontName=BOLD, fontSize=11, leading=12, textColor=INK_900)
S_BRAND_SUB = _style("brand_sub", fontSize=7.5, leading=9, textColor=INK_600)
S_EYEBROW = _style("eyebrow", fontName=BOLD, fontSize=8, leading=10, textColor=ACCENT, alignment=TA_RIGHT)
S_TITLE = _style("title", fontName=BOLD, fontSize=20, leading=24)
S_SUBTITLE = _style("subtitle", fontSize=10.5, leading=14, textColor=INK_600)
S_META_LABEL = _style("meta_label", fontName=BOLD, fontSize=6.5, leading=8, textColor=INK_600)
S_META_VALUE = _style("meta_value", fontName=BOLD, fontSize=10, leading=13)
S_TH = _style("th", fontName=BOLD, fontSize=8.5, leading=10.5, textColor=INK_900)
S_TH_SUB = _style("th_sub", fontSize=7, leading=9, textColor=INK_600)
S_RANK = _style("rank", fontName=BOLD, fontSize=14, leading=16, alignment=TA_CENTER)
S_NAME = _style("name", fontName=BOLD, fontSize=9.5, leading=12)
S_CELL = _style("cell", fontSize=9.5, leading=12)
S_TIER = _style("tier", fontSize=8.5, leading=11, textColor=INK_700)
S_REC = _style("rec", fontSize=8.5, leading=11)
S_SMALL = _style("small", fontSize=7.5, leading=9.5, textColor=INK_600)
S_FINAL = _style("final", fontName=BOLD, fontSize=13, leading=15)
S_NOTE = _style("note", fontSize=7.5, leading=10, textColor=INK_600)


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def _score(value: float) -> str:
    return f"{value:.2f}"


def _colour(c: colors.Color) -> str:
    return c.hexval().replace("0x", "#")


class _NumberedCanvas(pdf_canvas.Canvas):
    """Draws the footer once the page count is known, so every page can
    say "Page 2 of 3" -- a printed report gets separated from its pages."""

    def __init__(self, *args, footer_left: str = "", footer_mid: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved: list[dict] = []
        self._footer_left = footer_left
        self._footer_mid = footer_mid

    def showPage(self):  # noqa: N802 -- reportlab's name
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        width, _ = self._pagesize
        y = MARGIN * 0.55
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN, y + 11, width - MARGIN, y + 11)
        self.setFont(FONT, 7)
        self.setFillColor(INK_600)
        self.drawString(MARGIN, y, self._footer_left)
        self.drawCentredString(width / 2, y, self._footer_mid)
        self.drawRightString(width - MARGIN, y, f"Page {self._pageNumber} of {total}")


def _header(report: InterviewReport, width: float) -> list:
    logo = Image(str(_LOGO), width=24, height=24, mask="auto") if _LOGO.exists() else Spacer(24, 24)
    brand = Table(
        [[logo, [_p("ARKIVE", S_BRAND), _p("University HR", S_BRAND_SUB)], _p("INTERVIEW RESULTS REPORT", S_EYEBROW)]],
        colWidths=[30, width * 0.5, width * 0.5 - 30],
    )
    brand.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT),
            ]
        )
    )
    return [
        brand,
        Spacer(1, 10),
        _p(escape(report.job_title), S_TITLE),
        _p(escape(report.department), S_SUBTITLE),
        Spacer(1, 10),
    ]


def _meta(report: InterviewReport, width: float) -> Table:
    at = report.generated_at
    # built by hand: strftime's no-padding flags (%-d) don't exist on
    # Windows, where a teammate runs this
    generated = f"{at:%b} {at.day}, {at.year}, {at.hour % 12 or 12}:{at:%M} {at:%p}"
    cells = [
        ("CANDIDATES RANKED", str(len(report.entries))),
        ("INTERVIEW ROUNDS", str(len(report.rounds))),
        ("GENERATED", generated),
    ]
    table = Table(
        [[[_p(label, S_META_LABEL), Spacer(1, 3), _p(value, S_META_VALUE)] for label, value in cells]],
        colWidths=[width * 0.25, width * 0.25, width * 0.50],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WELL),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBEFORE", (1, 0), (-1, 0), 0.5, RULE),
            ]
        )
    )
    return table


def _cell(cell: InterviewReportCell, show_evaluator: bool) -> list:
    """The score, the form's General Evaluation for it (Qualified), then
    the interviewer's own recommendation -- "4.70 / Qualified / (Highly
    Recommended)", one per line. The final score column is the number
    alone."""
    if cell.score is None:
        parts = [_p(f'<font color="{_colour(INK_400)}">No scorecard</font>' if cell.no_scorecard else "–", S_CELL)]
    else:
        parts = [_p(f"<b>{_score(cell.score)}</b>", S_CELL)]
        if cell.tier_label:
            parts.append(_p(escape(cell.tier_label), S_TIER))
        if cell.recommendation_label:
            colour = _RECOMMENDATION_COLOUR.get(cell.recommendation or "", INK_700)
            parts.append(_p(f'<font color="{_colour(colour)}">({escape(cell.recommendation_label)})</font>', S_REC))
    if show_evaluator and cell.evaluator_name:
        parts.append(_p(escape(cell.evaluator_name), S_SMALL))
    return parts


def _ranking(report: InterviewReport, width: float) -> Table:
    # three rounds on portrait Letter leave each round ~101pt: room for
    # "(Highly Recommended)" (89pt at 8.5pt) on one line, and for a
    # three-part name beside them
    rank_w, name_w, final_w = 34, 125 if len(report.rounds) <= 3 else 120, 62
    round_w = (width - rank_w - name_w - final_w) / len(report.rounds)

    head = [_p("Rank", S_TH), _p("Interviewee", S_TH)]
    for r in report.rounds:
        heading = [_p(escape(r.label), S_TH)]
        if r.evaluator_name:
            heading.append(_p(escape(r.evaluator_name), S_TH_SUB))
        head.append(heading)
    head.append(_p("Final score", S_TH))

    rows = [head]
    for entry in report.entries:
        rank_colour = _colour(ACCENT if entry.rank == 1 else INK_900)
        row = [
            _p(f'<font color="{rank_colour}">{entry.rank}</font>', S_RANK),
            _p(escape(entry.applicant_name) + (" *" if entry.partial else ""), S_NAME),
        ]
        for r, cell in zip(report.rounds, entry.cells):
            row.append(_cell(cell, show_evaluator=r.evaluator_name is None))
        row.append(_p(_score(entry.final_score), S_FINAL))
        rows.append(row)

    table = Table(
        rows,
        colWidths=[rank_w, name_w] + [round_w] * len(report.rounds) + [final_w],
        repeatRows=1,
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), WELL),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK_900),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK_900),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, INK_900),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # the final score is the column the ranking is read from
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#fafafb")),
        ("LINEBEFORE", (-1, 0), (-1, -1), 0.5, RULE),
    ]
    for i in range(1, len(rows) - 1):
        style.append(("LINEBELOW", (0, i), (-1, i), 0.5, RULE))
    table.setStyle(TableStyle(style))
    return table


def render_interview_report_pdf(report: InterviewReport) -> bytes:
    """The ranking as PDF bytes, from an already-built InterviewReport
    (never the database): only the ranking table, in the shape of HR's
    "Interviewer Final Scoring" sheet. US Letter, portrait up to three
    rounds, landscape beyond. `report` must be ready; the caller checks."""
    pagesize = letter if len(report.rounds) <= 3 else landscape(letter)
    width = pagesize[0] - 2 * MARGIN

    story: list = []
    story += _header(report, width)
    story.append(_meta(report, width))
    story.append(Spacer(1, 16))
    story.append(_ranking(report, width))
    if any(entry.partial for entry in report.entries):
        story.append(Spacer(1, 6))
        story.append(_p("* A round has no scorecard, so the final score averages the rounds that were scored.", S_NOTE))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"Interview results: {report.job_title}",
        author="ARKIVE",
        subject="Interview results report",
    )
    footer_left = f"ARKIVE · Interview results · {report.job_title}"
    doc.build(
        story,
        canvasmaker=lambda *a, **k: _NumberedCanvas(
            *a, footer_left=footer_left, footer_mid="Confidential, for the hiring decision", **k
        ),
    )
    return buffer.getvalue()
