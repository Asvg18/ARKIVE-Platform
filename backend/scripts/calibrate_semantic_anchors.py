"""Measure where the semantic score's cosine anchors should sit.

The arithmetic half maps each requirement's best cosine (against any
résumé unit) onto 0-100 between _SEMANTIC_COSINE_FLOOR and
_SEMANTIC_COSINE_CEILING. This script embeds every labelled requirement
of scripts/eval/skill_matching_set.json against its pair's résumé, the
same way the score does, and prints the cosine distribution for each
label (met / partial / not_met). The floor belongs where not_met
requirements sit, the ceiling where met ones do.

With --floor and --ceiling it also prints, per pair, the arithmetic half
under the current anchors and under the proposed ones, and the match
score that gives beside the requirement coverage of a saved eval run.

Calls OpenAI's embeddings once per pair; writes nothing. Its labels are
drafts until HR reviews them (see scripts/eval_skill_matching.py).

Usage (from backend/):

    python -m scripts.calibrate_semantic_anchors
    python -m scripts.calibrate_semantic_anchors --floor 0.30 --ceiling 0.50
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

EVAL_DIR = Path(__file__).parent / "eval"
SET_PATH = EVAL_DIR / "skill_matching_set.json"
COVERAGE_RUN = EVAL_DIR / "results" / "v3-after-expansion-off.json"
LABELS = ("met", "partial", "not_met")


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _stretch(cosine: float, floor: float, ceiling: float) -> float:
    return max(0.0, min(100.0, (cosine - floor) / (ceiling - floor) * 100))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--floor", type=float, help="proposed cosine that scores 0")
    parser.add_argument("--ceiling", type=float, help="proposed cosine that scores 100")
    args = parser.parse_args()

    from app.domain.insights import MATCH_FLAG_THRESHOLD
    from app.models.application_resume import ApplicationResume
    from app.services import skill_matching as sm
    from app.services.skill_matching.scoring import (
        _COVERAGE_WEIGHT,
        _SEMANTIC_COSINE_CEILING,
        _SEMANTIC_COSINE_FLOOR,
        _SEMANTIC_WEIGHT,
        _score_requirements,
    )

    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    embeddings = sm._get_embeddings()
    cosines: dict[str, list[float]] = {label: [] for label in LABELS}
    # per pair: (cosine, keyword) for every requirement, labelled or not
    measured: dict[str, list[tuple[float, float]]] = {}

    for pair in data["pairs"]:
        resume = ApplicationResume(full_name="Candidate", raw_extracted_text="", **pair["resume"])
        requirements = [item["requirement"] for item in pair["labels"]]
        scored = _score_requirements(embeddings, requirements, sm._resume_units(resume))
        measured[pair["id"]] = [(cosine, keyword) for _, keyword, cosine, _ in scored]
        for item, (_, _, cosine, _) in zip(pair["labels"], scored):
            # a requirement not yet labelled tells us nothing
            if item.get("label") in cosines:
                cosines[item["label"]].append(cosine)

    floor, ceiling = _SEMANTIC_COSINE_FLOOR, _SEMANTIC_COSINE_CEILING
    proposed = args.floor is not None and args.ceiling is not None
    print(f"Current anchors: floor {floor}, ceiling {ceiling}")
    if proposed:
        print(f"Proposed anchors: floor {args.floor}, ceiling {args.ceiling}")
    print(f"\n{'label':<8} {'n':>4} {'p10':>6} {'p25':>6} {'median':>7} {'p75':>6} {'p90':>6}   semantic at median")
    for label in LABELS:
        values = cosines[label]
        if not values:
            continue
        median = statistics.median(values)
        at_median = f"{_stretch(median, floor, ceiling):.0f}"
        if proposed:
            at_median += f" -> {_stretch(median, args.floor, args.ceiling):.0f}"
        print(
            f"{label:<8} {len(values):>4} {_quantile(values, 0.10):>6.3f} {_quantile(values, 0.25):>6.3f} "
            f"{median:>7.3f} {_quantile(values, 0.75):>6.3f} {_quantile(values, 0.90):>6.3f}   {at_median}"
        )

    if not proposed:
        return

    coverage = {}
    if COVERAGE_RUN.exists():
        run = json.loads(COVERAGE_RUN.read_text(encoding="utf-8"))["runs"][0]
        coverage = {result["id"]: result["requirement_coverage"] for result in run}

    def arithmetic(rows: list[tuple[float, float]], lo: float, hi: float) -> float:
        return statistics.mean(
            _SEMANTIC_WEIGHT * _stretch(cosine, lo, hi) + (1 - _SEMANTIC_WEIGHT) * keyword for cosine, keyword in rows
        )

    print(f"\n{'pair':<10} {'text similarity':>16} {'coverage':>9} {'match':>14}  (flagged below {MATCH_FLAG_THRESHOLD})")
    for pair_id, rows in measured.items():
        before, after = arithmetic(rows, floor, ceiling), arithmetic(rows, args.floor, args.ceiling)
        line = f"{pair_id:<10} {before:>7.1f} -> {after:<6.1f}"
        if coverage.get(pair_id) is not None:
            cov = coverage[pair_id]
            match_before = (1 - _COVERAGE_WEIGHT) * before + _COVERAGE_WEIGHT * cov
            match_after = (1 - _COVERAGE_WEIGHT) * after + _COVERAGE_WEIGHT * cov
            marks = "".join("*" if m < MATCH_FLAG_THRESHOLD else " " for m in (match_before, match_after))
            line += f" {cov:>9.1f} {match_before:>5.1f}{marks[0]} -> {match_after:.1f}{marks[1]}"
        print(line)


if __name__ == "__main__":
    main()
