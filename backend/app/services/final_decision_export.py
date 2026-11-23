"""Excel export of the Final Decision Board."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.schemas.pipeline import FinalDecisionBoardResponse

_COLUMNS = [
    ("Candidate Name", 28),
    ("Rank", 8),
    ("Match Score", 16),
    ("Evaluator Consensus Score", 24),
    ("Exam Percentile", 16),
    ("Interview Rubric Score", 20),
]


def build_final_decision_board_workbook(board: FinalDecisionBoardResponse) -> bytes:
    """Built from the already-built board, never the database, so it
    matches the screen. `entries` is already ranked; the rank column is
    that order. Null scores are blank cells, not "N/A", so the columns
    stay numeric. No Final Synthesis Score column, as on the board: the
    HR Director's office could not confirm how it is computed."""
    workbook = Workbook()
    sheet = workbook.active
    # Excel caps sheet names at 31 characters and rejects a handful of
    # punctuation marks -- truncated and stripped rather than letting a
    # long or oddly-punctuated job title fail the whole export.
    sheet.title = "".join(c for c in board.job_title if c not in r'\/*?:[]')[:31] or "Final Decision Board"

    for col_index, (label, width) in enumerate(_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col_index, value=label)
        cell.font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(col_index)].width = width

    for row_index, entry in enumerate(board.entries, start=2):
        rank = row_index - 1
        values = [
            entry.applicant_name,
            rank,
            entry.skill_match_score,
            entry.executive_consensus_score,
            entry.exam_percentile,
            entry.interview_rubric_score,
        ]
        for col_index, value in enumerate(values, start=1):
            sheet.cell(row=row_index, column=col_index, value=value)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_filename(job_title: str) -> str:
    """A safe filename, not the job title verbatim -- HR is free to name
    a job anything, including characters no filesystem or browser
    Content-Disposition header would accept unescaped."""
    safe = "".join(c if c.isalnum() else "-" for c in job_title).strip("-") or "job"
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"final-decision-board-{safe.lower()}.xlsx"
