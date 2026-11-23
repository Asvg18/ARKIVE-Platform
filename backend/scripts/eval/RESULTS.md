# Skill matching evaluation — 18 Oct 2026

> **The labels are drafts.** They were written by Claude from the résumé text
> and have not yet been confirmed by HR. Until `reviewed_by` is set in
> `skill_matching_set.json`, treat every number below as provisional and do
> not quote it as a finding. To review: `python -m scripts.eval_skill_matching
> export-review labels.csv`, have HR fill the `hr_label` column, then
> `import-review labels.csv --by "<name>"` and re-run the report.

## What was measured

How often the Skill Matching Agent's per-requirement verdict (met / partly
met / not met) agrees with a person's, on 15 résumé–job pairs from the dev
database — 163 labelled requirements (98 met, 35 partly met, 30 not met).
12 pairs are applications as submitted; 3 are a real résumé set against a
different real job, added so the set has requirements a résumé genuinely
does not meet (otherwise over-generosity could not be measured).

The verdict compared is the one the score counted: a verdict whose quoted
evidence failed the quote check counts as not met, because that is what it
earned. Each configuration scored every pair twice.

| Version | Query expansion | Exact agreement | Weighted κ | Missed¹ | Under-credited | Invented² | Over-credited | Coverage error³ | Same verdict both runs | s / applicant |
|---|---|---|---|---|---|---|---|---|---|---|
| v2 (before) | off | 69.6% | 0.57 | 17.7% | 21.2% | 1.7% | 9.2% | 13.2 pts | 73.2% | 46 |
| v2 (before) | on  | 66.0% | 0.51 | 23.7% | 25.8% | 1.7% | 8.3% | 17.0 pts | 75.6% | 56 |
| v3, first cut | off | 70.2% | 0.59 | 11.7% | 17.8% | 8.3% | 12.0% | 14.2 pts | 78.7% | 54 |
| v3, first cut | on  | 70.9% | 0.60 | 15.4% | 19.6% | 10.0% | 9.5% | 13.4 pts | 79.3% | 64 |
| **v3 (after)** | **off** | **75.8%** | **0.66** | **8.3%** | **13.5%** | 5.0% | 10.7% | **11.7 pts** | **84.1%** | 55 |
| v3 (after) | on  | 76.1% | 0.66 | 9.4% | 14.7% | 3.3% | 9.2% | 12.1 pts | 80.5% | 67 |

¹ Requirements the résumé does meet (fully or partly) that were scored not met — the "too strict" error.
² Requirements the résumé does not meet that were given credit — the "too generous" error (of 60 such verdicts).
³ Mean absolute difference between the requirement-coverage half of the score and the labels' coverage, per application.

## Reading it

- **Strictness roughly halved.** Missed requirements fell from 17.7% to 8.3%,
  and agreement with the labels rose from 69.6% to 75.8% (κ 0.57 → 0.66,
  "moderate" to "substantial").
- **The cost is a little generosity.** Invented credit rose from 1 verdict in
  60 to 3 in 60 — mostly a Computer Science teacher given partial credit for
  "debugging a large codebase", which a reviewer could label either way.
- **More repeatable.** The same verdict on both runs went from 73% to 84% of
  requirements, largely because degree requirements are now settled by a
  rule rather than by the model.
- **Query expansion does not help** on this set — level with v3, worse with
  v2 — and adds ~12 s per applicant, so it stays off by default.
- The first v3 cut showed where the remaining errors were; the second fixed
  three of them: correct verdicts lost to a character-for-character quote
  check, a correct degree `met` overturned by the re-check, and partial
  credit for experience in a role never held.

## Limits

15 pairs from a small dev database, several sharing one résumé; one labeller,
not yet HR. Differences of a few points between rows are within run-to-run
noise (the "same verdict both runs" column is the measure of it). Only the
verdicts are evaluated, not the arithmetic half of the score.

## Reproduce

```
docker compose exec backend python -m scripts.eval_skill_matching run --name v3-after --expansion off --repeat 2
docker compose exec backend sh -c 'python -m scripts.eval_skill_matching report scripts/eval/results/*.json'
```

The older version is measured by putting its `app` package first on
`PYTHONPATH` (see the script's docstring). Roughly ten gpt-4o-mini calls per
pair per run.
