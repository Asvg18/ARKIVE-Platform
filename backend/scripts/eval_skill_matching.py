"""Measure the Skill Matching Agent against labelled résumé/job pairs.

The set is scripts/eval/skill_matching_set.json: real résumés and jobs
from the dev database (contact details removed), each requirement
labelled met / partial / not_met by a person. Its labels must be
reviewed by HR before a result is quoted -- the file says whether they
have been.

Two modes:

  run     Score every pair with the code on the import path and write
          each requirement's verdict to a results file. Calls OpenAI
          (gpt-4o-mini and text-embedding-3-small; roughly ten calls a
          pair). Nothing is written to the database: the résumé and job
          are built in memory, the agent-run log and the "other
          openings" suggestions are switched off.

  report  Compare one or more results files with the labels.

  export-review / import-review
          The labels as a spreadsheet for HR to confirm or correct, and
          their corrections read back in.

Usage (from backend/, or `docker compose exec backend ...`):

    python -m scripts.eval_skill_matching run --name v3-expansion --expansion on --repeat 2
    python -m scripts.eval_skill_matching report scripts/eval/results/*.json

To measure an older version, put its `app` package first on PYTHONPATH
(e.g. `git archive HEAD backend/app | tar -x -C /tmp/baseline
--strip-components=1`, then PYTHONPATH=/tmp/baseline) -- this script
only uses what every version since score_method v2 has.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SET_PATH = Path(__file__).parent / "eval" / "skill_matching_set.json"
RESULTS_DIR = Path(__file__).parent / "eval" / "results"
POINTS = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
ORDER = ["not_met", "partial", "met"]


# --------------------------------------------------------------------- run


def _score_pair(pair: dict) -> dict:
    from app.infra.db import SessionLocal
    from app.models.application_resume import ApplicationResume
    from app.models.job_requisition import JobRequisition
    from app.services import skill_matching as sm

    resume = ApplicationResume(full_name="Candidate", raw_extracted_text="", **pair["resume"])
    job = JobRequisition(**pair["job"])
    db = SessionLocal()
    started = time.monotonic()
    try:
        result = sm.run_skill_matching(db, resume=resume, target_requisition=job)
    finally:
        db.rollback()
        db.close()
    by_requirement = {check.requirement: check for check in result.requirement_checks}
    rows = []
    for item in pair["labels"]:
        check = by_requirement.get(item["requirement"])
        verdict = check.verdict if check else "not_met"
        verified = bool(check and check.verified)
        rows.append(
            {
                "requirement": item["requirement"],
                "verdict": verdict,
                "verified": verified,
                # what the score counted: an unverified verdict earns nothing
                "counted": verdict if verified else "not_met",
                "basis": getattr(check, "basis", "") if check else "",
            }
        )
    return {
        "id": pair["id"],
        "match_score": result.match_score,
        "arithmetic_score": result.arithmetic_score,
        "requirement_coverage": result.requirement_coverage,
        "terminal_state": result.rag_trace.terminal_state if result.rag_trace else "",
        "seconds": round(time.monotonic() - started, 1),
        "requirements": rows,
    }


def run(args) -> None:
    from app.infra.config import settings
    from app.services import skill_matching as sm

    settings.rag_query_expansion = args.expansion == "on"
    # nothing reaches the database, and no other job is looked at
    sm.SKILL_MATCHING.log = lambda *a, **k: None
    sm._suggest_other_openings = lambda *a, **k: []

    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    pairs = [p for p in data["pairs"] if not args.only or p["id"] in args.only]
    runs = []
    for attempt in range(1, args.repeat + 1):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            scored = list(pool.map(_score_pair, pairs))
        runs.append(scored)
        print(f"[{args.name}] run {attempt}/{args.repeat}: {len(scored)} pairs", file=sys.stderr)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{args.name}.json"
    out.write_text(
        json.dumps(
            {
                "name": args.name,
                "score_method": sm.SCORE_METHOD,
                "query_expansion": settings.rag_query_expansion,
                "labels_reviewed_by": data.get("reviewed_by"),
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out)


# ------------------------------------------------------------------ report


def _kappa(pairs: list[tuple[str, str]]) -> float:
    """Linearly weighted Cohen's kappa over the ordered verdicts
    not_met < partial < met: agreement beyond chance, where calling a
    partial a met is half as wrong as calling a not_met a met."""
    k = len(ORDER)
    index = {v: i for i, v in enumerate(ORDER)}
    n = len(pairs)
    if not n:
        return float("nan")
    observed = [[0.0] * k for _ in range(k)]
    for truth, predicted in pairs:
        observed[index[truth]][index[predicted]] += 1
    rows = [sum(r) for r in observed]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    weight = lambda i, j: abs(i - j) / (k - 1)  # noqa: E731
    disagreement = sum(weight(i, j) * observed[i][j] for i in range(k) for j in range(k)) / n
    chance = sum(weight(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k)) / (n * n)
    return 1 - disagreement / chance if chance else float("nan")


def _metrics(results: dict, labels: dict) -> dict:
    compared: list[tuple[str, str]] = []
    coverage_errors: list[float] = []
    for run_ in results["runs"]:
        for pair in run_:
            truth = labels[pair["id"]]
            label_points, predicted_points = [], []
            for row in pair["requirements"]:
                label = truth.get(row["requirement"])
                if label is None:
                    continue
                compared.append((label, row["counted"]))
                label_points.append(POINTS[label])
                predicted_points.append(POINTS[row["counted"]])
            if label_points:
                coverage_errors.append(
                    abs(sum(predicted_points) - sum(label_points)) / len(label_points) * 100
                )
    n = len(compared)
    positives = [(t, p) for t, p in compared if t != "not_met"]
    negatives = [(t, p) for t, p in compared if t == "not_met"]
    return {
        "requirements": n,
        "exact": sum(t == p for t, p in compared) / n,
        "kappa": _kappa(compared),
        # too strict: something the résumé does show, given nothing
        "missed": sum(p == "not_met" for _, p in positives) / len(positives) if positives else float("nan"),
        "under": sum(POINTS[p] < POINTS[t] for t, p in compared) / n,
        # too generous: something the résumé does not show, credited
        "invented": sum(p != "not_met" for _, p in negatives) / len(negatives) if negatives else float("nan"),
        "over": sum(POINTS[p] > POINTS[t] for t, p in compared) / n,
        "coverage_mae": sum(coverage_errors) / len(coverage_errors),
        "stability": _stability(results),
        "seconds": _mean([p["seconds"] for r in results["runs"] for p in r]),
    }


def _stability(results: dict) -> float:
    """Share of requirements given the same verdict in every run."""
    runs = results["runs"]
    if len(runs) < 2:
        return float("nan")
    same = total = 0
    by_run = [{p["id"]: p for p in r} for r in runs]
    for pair_id, first in by_run[0].items():
        for i, row in enumerate(first["requirements"]):
            total += 1
            same += all(r[pair_id]["requirements"][i]["counted"] == row["counted"] for r in by_run[1:])
    return same / total


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def _pct(value: float) -> str:
    return "—" if math.isnan(value) else f"{value * 100:.1f}%"


def report(args) -> None:
    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    labels = {
        pair["id"]: {item["requirement"]: item["label"] for item in pair["labels"]} for pair in data["pairs"]
    }
    print(
        f"Labels: {sum(1 for p in labels.values() for v in p.values() if v)} requirements over "
        f"{len(labels)} pairs; reviewed by: {data.get('reviewed_by') or 'NOT YET REVIEWED (draft labels)'}\n"
    )
    header = (
        "| Version | Expansion | Runs | Exact agreement | Weighted κ | Missed (true → not met) | "
        "Under-credited | Invented (false → credited) | Over-credited | Coverage error | Stable across runs | Sec/pair |"
    )
    print(header)
    print("|" + "---|" * (header.count("|") - 1))
    for path in args.files:
        results = json.loads(Path(path).read_text(encoding="utf-8"))
        m = _metrics(results, labels)
        print(
            f"| {results['name']} ({results['score_method']}) | {'on' if results['query_expansion'] else 'off'} "
            f"| {len(results['runs'])} | {_pct(m['exact'])} | {m['kappa']:.2f} | {_pct(m['missed'])} "
            f"| {_pct(m['under'])} | {_pct(m['invented'])} | {_pct(m['over'])} | {m['coverage_mae']:.1f} pts "
            f"| {_pct(m['stability'])} | {m['seconds']:.0f} |"
        )


# ------------------------------------------------------- HR label review


REVIEW_COLUMNS = ["pair", "job", "requirement", "draft_label", "draft_note", "hr_label", "hr_note"]


def export_review(args) -> None:
    """The labels as a spreadsheet for HR: one row per requirement, with
    the draft label and an empty column for theirs. The résumé text is
    in the set file; the pair id names the application it came from."""
    import csv

    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for pair in data["pairs"]:
            for item in pair["labels"]:
                writer.writerow(
                    {
                        "pair": pair["id"],
                        "job": pair["job"]["title"],
                        "requirement": item["requirement"],
                        "draft_label": item["label"] or "",
                        "draft_note": item["note"],
                        "hr_label": "",
                        "hr_note": "",
                    }
                )
    print(args.csv)


def import_review(args) -> None:
    """Takes HR's labels back from the spreadsheet: a filled hr_label
    (met / partial / not_met, or "skip" to leave a requirement out)
    replaces the draft, and the set is marked reviewed by `--by`."""
    import csv

    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    items = {(p["id"], item["requirement"]): item for p in data["pairs"] for item in p["labels"]}
    changed = 0
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            label = (row.get("hr_label") or "").strip().lower().replace(" ", "_")
            if not label:
                continue
            if label not in {"met", "partial", "not_met", "skip"}:
                sys.exit(f"Unknown label {label!r} for {row['pair']}: {row['requirement']}")
            item = items[(row["pair"], row["requirement"])]
            new = None if label == "skip" else label
            changed += item["label"] != new
            item["label"] = new
            if (row.get("hr_note") or "").strip():
                item["note"] = row["hr_note"].strip()
    data["reviewed_by"] = args.by
    SET_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{changed} labels changed; set marked reviewed by {args.by}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--name", required=True)
    run_parser.add_argument("--expansion", choices=["on", "off"], required=True)
    run_parser.add_argument("--repeat", type=int, default=1)
    run_parser.add_argument("--workers", type=int, default=4)
    run_parser.add_argument("--only", nargs="*", help="pair ids to run (default: all)")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("files", nargs="+")
    export_parser = sub.add_parser("export-review")
    export_parser.add_argument("csv")
    import_parser = sub.add_parser("import-review")
    import_parser.add_argument("csv")
    import_parser.add_argument("--by", required=True, help="who reviewed the labels")
    args = parser.parse_args()
    {"run": run, "report": report, "export-review": export_review, "import-review": import_review}[args.mode](args)


if __name__ == "__main__":
    main()
