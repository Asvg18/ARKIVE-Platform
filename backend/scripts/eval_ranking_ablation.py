"""Does ARKIVE's ranking agree with a human HR ranking, and which part of
the retrieval design earns it?

Scores one job's applicants under four retrieval variants, using the
résumé and job text exactly as the Skill Matching Agent reads them, and
compares each variant's ranking with a reference ranking by Spearman's
rho and NDCG@5.

  dense    100% semantic  (arithmetic half, weights 1.0 / 0.0)
  sparse   100% BM25      (arithmetic half, weights 0.0 / 1.0)
  hybrid   the current 60/40 (skill_matching._SEMANTIC_WEIGHT)
  no_rag   no rubric: cosine of the whole résumé against the whole job

The first three score every requirement line of the job against the
résumé's evidence units (skill_matching._score_requirements), then
average -- the arithmetic half of the match score, with only the
semantic/keyword weights changed. The model-judged coverage half is the
same under all three, so it is left out. no_rag embeds the two documents
whole and takes one cosine.

Two steps, so the (paid) résumé reading is done once:

  extract   Read each image/PDF in --resumes with the app's own
            extract_resume (the intake the applicants went through) and
            save the structured forms to --forms.
  score     Rank those forms and write the comparison.

Usage (from backend/):

    python -m scripts.eval_ranking_ablation extract --resumes DIR --forms forms.json
    python -m scripts.eval_ranking_ablation score --forms forms.json --job job.json \
        --reference reference.json --out results.json

job.json:        {title, department, description, qualifications, requirements}
reference.json:  {"reference": "MSEUF HRD", "ranking": [names, best first],
                  "others": {"label": [names, best first], ...}}
"""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


# ------------------------------------------------------------------ extract


def _image_to_pdf(path: Path) -> bytes:
    """One page, one embedded image -- what a phone scan or an
    image-to-PDF export looks like to the app's reader."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, format="PDF")
    return buffer.getvalue()


def extract(args) -> None:
    from app.services.resume_extraction import extract_resume

    forms = {}
    for path in sorted(Path(args.resumes).iterdir()):
        if path.suffix.lower() in IMAGE_SUFFIXES:
            pdf_bytes = _image_to_pdf(path)
        elif path.suffix.lower() == ".pdf":
            pdf_bytes = path.read_bytes()
        else:
            continue
        form = extract_resume(pdf_bytes).model_dump()
        # the file name is the candidate's name in the reference ranking
        forms[path.stem] = form
        print(f"{path.stem}: {len(form['experience'])} jobs, {len(form['education'])} schools, "
              f"{len(form['skills'])} skills", flush=True)
    Path(args.forms).write_text(json.dumps(forms, ensure_ascii=False, indent=2), encoding="utf-8")


# -------------------------------------------------------------------- score


def _cosine(a: list[float], b: list[float]) -> float:
    from app.services.skill_matching import _cosine_similarity

    return _cosine_similarity(a, b)


def score_candidates(forms: dict, job_fields: dict) -> dict[str, dict[str, float]]:
    from app.models.application_resume import ApplicationResume
    from app.models.job_requisition import JobRequisition
    from app.services import skill_matching as sm

    embeddings = sm._get_embeddings()
    job = JobRequisition(**job_fields)
    requirements, real_lines = sm._target_requirements(job)
    if not real_lines:
        raise SystemExit("the job has no requirement lines; the per-requirement variants need them")
    job_vector = sm._embed(embeddings, [sm._requisition_corpus_text(job)])[0]

    scores: dict[str, dict[str, float]] = {}
    for name, form in forms.items():
        resume = ApplicationResume(
            raw_extracted_text="",
            **{k: form[k] for k in (
                "full_name", "email", "phone", "location", "linkedin_url", "portfolio_url",
                "professional_summary", "education", "experience", "skills", "certifications",
                "additional_sections",
            )},
        )
        per_requirement = sm._score_requirements(embeddings, requirements, sm._resume_units(resume))
        semantic = sm._mean(s for s, _, _, _ in per_requirement)
        keyword = sm._mean(k for _, k, _, _ in per_requirement)
        resume_vector = sm._embed(embeddings, [sm._resume_scoring_text(resume)])[0]
        scores[name] = {
            "dense": semantic,
            "sparse": keyword,
            "hybrid": sm._SEMANTIC_WEIGHT * semantic + (1 - sm._SEMANTIC_WEIGHT) * keyword,
            "no_rag": _cosine(resume_vector, job_vector) * 100,
        }
    return scores


# ------------------------------------------------------------------ metrics


def _average_ranks(values: list[float]) -> list[float]:
    """1 = highest value; tied values share the mean of the positions
    they occupy, which is the form Spearman's rho needs."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(reference_ranks: list[float], other_ranks: list[float]) -> float:
    """Pearson correlation of the two rank vectors -- equal to
    1 - 6*sum(d^2)/(n(n^2-1)) when there are no ties, and still right
    when there are."""
    n = len(reference_ranks)
    mean_a, mean_b = sum(reference_ranks) / n, sum(other_ranks) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(reference_ranks, other_ranks))
    var_a = sum((a - mean_a) ** 2 for a in reference_ranks)
    var_b = sum((b - mean_b) ** 2 for b in other_ranks)
    return cov / math.sqrt(var_a * var_b) if var_a and var_b else float("nan")


def ndcg_at_k(predicted: list[str], gain: dict[str, float], k: int) -> float:
    """Gain of the reference ranking at each predicted position,
    discounted by log2(position + 1), over the best possible ordering."""
    dcg = sum(gain[name] / math.log2(pos + 2) for pos, name in enumerate(predicted[:k]))
    ideal = sorted(gain.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(pos + 2) for pos, g in enumerate(ideal))
    return dcg / idcg


def _order(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda name: -scores[name])


def compare(candidate_order: list[str], reference_order: list[str], k: int = 5) -> dict:
    ref_rank = {name: i + 1 for i, name in enumerate(reference_order)}
    names = list(reference_order)
    cand_rank = {name: i + 1 for i, name in enumerate(candidate_order)}
    n = len(names)
    graded = {name: float(n - ref_rank[name] + 1) for name in names}  # 10 for rank 1 ... 1 for rank 10
    binary = {name: 1.0 if ref_rank[name] <= k else 0.0 for name in names}
    return {
        "rho": spearman([ref_rank[x] for x in names], [cand_rank[x] for x in names]),
        "ndcg5": ndcg_at_k(candidate_order, graded, k),
        "ndcg5_binary": ndcg_at_k(candidate_order, binary, k),
        "top5_overlap": len(set(candidate_order[:k]) & set(reference_order[:k])),
    }


def score(args) -> None:
    forms = json.loads(Path(args.forms).read_text(encoding="utf-8"))
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    ref_order = reference["ranking"]
    missing = set(ref_order) ^ set(forms)
    if missing:
        raise SystemExit(f"names in only one of forms/reference: {sorted(missing)}")

    scores = score_candidates(forms, job)
    variants = {
        "Dense only (100% semantic)": "dense",
        "Sparse only (100% BM25)": "sparse",
        "Hybrid RAG (60/40)": "hybrid",
        "No-RAG baseline (whole-document cosine)": "no_rag",
    }
    rows = []
    for label, key in variants.items():
        order = _order({name: s[key] for name, s in scores.items()})
        rows.append({"variant": label, "order": order, **compare(order, ref_order),
                     "scores": {name: round(s[key], 2) for name, s in scores.items()}})
    for label, order in (reference.get("others") or {}).items():
        rows.append({"variant": label, "order": order, **compare(order, ref_order), "scores": None})

    out = {"reference": reference["reference"], "reference_order": ref_order, "rows": rows}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Reference: {reference['reference']}\n")
    print("| Variant | Spearman rho | NDCG@5 | NDCG@5 (binary) | Top-5 overlap |")
    print("|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['variant']} | {row['rho']:.3f} | {row['ndcg5']:.3f} | {row['ndcg5_binary']:.3f} "
              f"| {row['top5_overlap']}/5 |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("--resumes", required=True)
    ex.add_argument("--forms", required=True)
    sc = sub.add_parser("score")
    sc.add_argument("--forms", required=True)
    sc.add_argument("--job", required=True)
    sc.add_argument("--reference", required=True)
    sc.add_argument("--out", required=True)
    args = parser.parse_args()
    {"extract": extract, "score": score}[args.mode](args)


if __name__ == "__main__":
    main()
