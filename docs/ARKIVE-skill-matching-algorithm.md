# ARKIVE skill matching algorithm

The one maintained description of how the Skill Matching Agent scores a résumé against the job it was submitted for. Checked against the code on 29 Oct 2026 (`score_method` `"applied_job_v4"`).

The code comments link here instead of repeating it. When the code and this file disagree, the code is right and this file is fixed. The measured results live in [`backend/scripts/eval/RESULTS.md`](../backend/scripts/eval/RESULTS.md), produced by `backend/scripts/eval_skill_matching.py`; this file explains the method and points there for the numbers.

| Part | Where |
|---|---|
| Running the agent, the blend, suggestions | `backend/app/services/skill_matching/__init__.py` |
| Tokenizing, evidence units, hybrid retrieval, the arithmetic score, prompts | `text.py`, `evidence.py`, `retrieval.py`, `scoring.py`, `prompts.py` in the same package |
| The retrieval graph and verdict settling | `backend/app/services/rag_pipeline.py` |
| The agents inside that graph | `backend/app/services/agents/rag_catalog.py` |
| The retrieval automaton (states and transitions) | `backend/app/domain/rag_dfa.py` |
| The flag threshold | `backend/app/domain/insights.py` (`MATCH_FLAG_THRESHOLD`) |
| What is sent to the model, locked character for character | `backend/tests/test_ai_instruction_lock.py` |

## 1. The score

```text
match = 0.5 × arithmetic + 0.5 × requirement coverage
```

Both halves read the résumé the applicant reviewed and submitted (`ApplicationResume`), never the raw text recovered from the PDF, and both compare it with **the applied-to job only**. Other open jobs play no part in the score.

### 1.1 The arithmetic half (no model)

For each requirement line of the job:

1. **Semantic score.** The requirement and every résumé unit are embedded (`text-embedding-3-small`, one call for all of them). The unit with the highest cosine similarity is the closest résumé line. That cosine is stretched onto 0 to 100 between two anchors, `_SEMANTIC_COSINE_FLOOR = 0.30` and `_SEMANTIC_COSINE_CEILING = 0.50`, and clamped outside them.
2. **Keyword score.** BM25 of the requirement against the résumé units, as a share of the best score that requirement could get: the requirement scored against itself, with the requirement lines added to the corpus so every word has an idf. This puts a short and a long résumé on the same 0 to 100 scale. When BM25 has no signal (a tiny corpus), the share of the requirement's words found in the résumé stands in.
3. **Combined:** `0.6 × semantic + 0.4 × keyword` (`_SEMANTIC_WEIGHT = 0.6`). The semantic side weighs more because it catches conceptual matches BM25 cannot ("built LLM-backed tools" for "AI/ML experience").

The arithmetic half is the mean of the per-requirement combined scores.

**BM25 details.** `_bm25_scores` uses BM25Okapi's formula with `k1 = 1.5`, `b = 0.75`, but Lucene's idf, `log(1 + (N − n + 0.5) / (n + 0.5))`, which stays positive however common a word is. Okapi's idf falls to zero for a word in half the corpus, which, with the requirement in the corpus beside a short résumé, scored the closest matches lowest.

**Normalisation before tokenising** (applied to requirement and résumé alike, so it can only make them agree more):

- Degree titles and abbreviations fold onto one form (`_DEGREE_FORMS`): "M.S. in", "MS in", "Master's" become `master`; "BSCS" becomes `bachelor science computer science`. "MS" and "BS" fold only before "in"/"of", so "MS Office" stays a product. Compound titles are matched before the bare letters they start with.
- Plurals fold onto the singular (`_stem`), leaving "-ss", "-us", "-is" endings and short words alone.
- Leading bullets and list numbers are stripped, but a line starting "5+ years" is not.

### 1.2 The coverage half (the agents)

The Scoring Agent gives each requirement a verdict, `met`, `partial` or `not_met`, with the exact words of the evidence it rests on, a `basis` (`direct`, `equivalent`, `related`, `transferable`, `none`) and one sentence of reasoning. The verdicts are then settled (section 3.3) and scored:

| Verdict | Points |
|---|---|
| `met`, verified | 1 |
| `partial`, verified | 0.5 |
| `not_met`, or any verdict not verified | 0 |

Coverage = mean points × 100. A requirement with no verdict counts as 0.

The model never writes a number and is never shown the arithmetic half, so its verdicts are an independent second look. The per-requirement semantic scores are used only to decide which `not_met` verdicts get re-checked.

### 1.3 The blend and its fall-back

- If there are verdicts, `match = 0.5 × arithmetic + 0.5 × coverage` (`_COVERAGE_WEIGHT = 0.5`).
- If there are none (the pipeline ended in `rejected`, so nothing was retrieved to judge), `match = arithmetic`.

Whether the Critic signed off the **written assessment** (strengths, gaps, summary) does not decide whether the verdicts count. The verdicts are audited separately (section 3.3), so they count either way. An assessment the Critic did not sign off is shown to HR marked Unverified.

### 1.4 The flag

An application is flagged when `round(match, 1) < MATCH_FLAG_THRESHOLD` (60). That is the only flag reason (`flag_reason = "below_threshold"`). An unverified assessment does not flag an application on its own: it is a statement about the assessment, not the candidate, and HR still sees it marked Unverified.

The threshold lives in `domain/insights.py`, not in the skill matching module, because the Synthesis screen describes it to HR in words; one constant keeps the description and the behaviour together.

### 1.5 What HR is shown

`SkillMatchResult.requirement_scores` holds one row per requirement: the semantic, keyword and combined scores, the closest résumé line, and the verdict with its basis, reasoning, quote, whether it was verified, and the points it earned. This is the rubric behind the number.

### 1.6 Other openings

Only for an applicant who scored below the threshold, ARKIVE suggests up to three (`_SUGGESTION_LIMIT`) other openings they may fit better, limited to openings they can still apply to. This is a separate whole-résumé ranking. It runs after the score and never feeds back into it.

## 2. Retrieval

The written assessment and the verdicts are produced from retrieved evidence, never from the whole résumé.

1. **Requirement chunks.** The job's qualification lines, one chunk each (`_chunk_jd_requirements`).
2. **Evidence chunks.** Built from the résumé's structured fields rather than re-parsed text: each experience, education, skills group, certification, and each line of an additional section, headed by its section. A licence or eligibility section counts as a credential.
3. **Hybrid retrieval.** For each requirement, BM25 and embedding similarity each rank the evidence chunks; the two rankings are fused with **Reciprocal Rank Fusion**, `score = Σ 1 / (60 + rank)`. The top `_RETRIEVAL_TOP_K = 3` chunks are kept. (LangChain's `EnsembleRetriever` no longer exists, so `_fuse_rankings` implements RRF directly.)
4. **Section evidence.** A degree requirement is always shown the résumé's education entries, and a licence or certification requirement its credentials (up to `_SECTION_EVIDENCE_LIMIT = 3`), appended after what retrieval found. Retrieval ranks by likeness of words, and a degree requirement's verdict can only be as good as the degrees it is shown.
5. **Role context and reading rule.** Every agent that judges a requirement is told what the role is (`_role_context`) and how to read a requirement (`_REQUIREMENT_READING_RULE`): options joined by "or" are alternatives; a higher qualification meets a lower one of the same kind; equivalent names count; meaning, not wording, is judged.
6. **Query expansion (off).** `settings.rag_query_expansion` lets one model call rewrite each requirement into search phrasings closer to how evidence is written, fused with the plain requirement by RRF so a bad phrasing can only dilute, never displace, it. It is off by default: on the labelled set it gave no measurable gain and added about 12 seconds per applicant (see `RESULTS.md`). With it off, behaviour is exactly as before the setting existed.

## 3. The retrieval automaton

The coverage half and the written assessment come from a LangGraph `StateGraph` of seven agents. Which agent runs next is decided by a transition table held as plain data in `domain/rag_dfa.py`; `rag_pipeline.py` only wires the table to the nodes. `tests/test_rag_dfa.py` asserts that the compiled graph's edges are exactly the table's.

### 3.1 States and transitions

```text
START -> ingestion -> validation --(no usable evidence)--> rejected -> END
                          |
                       (usable)
                          v
                     compliance -> context_routing -> scoring -> audit
                                                         ^          |
                                              (retry)    |          +--(grounded)--> END
                                                         |          |
                                                       clarify <----+--(unsupported, retry possible)
                                                         |          |
                                          (budget spent) |          +--(unsupported, retry cannot help)
                                                         v          v
                                                      manual_review -> END
```

| State | Agent | Job |
|---|---|---|
| `ingestion` | IngestionAgent | Builds the evidence chunks |
| `validation` | ValidationAgent | Stops when there is nothing usable to retrieve over |
| `compliance` | ComplianceAgent | Blinds the evidence (removes identity details) before any judgement |
| `context_routing` | ContextRouterAgent | Builds the queries and retrieves evidence per requirement |
| `scoring` | ScoringAgent | Writes the assessment and one verdict per requirement |
| `audit` | AuditAgent (the Critic) | Checks the written assessment against the retrieved evidence |
| `clarify` | ClarifyAgent | Answers the Critic's objections with wider retrieval, then sends the draft back to scoring |
| `rejected`, `manual_review` | none | Dead ends: the result is shown to HR as unverified |

### 3.2 Invariants the code and tests keep

- **Scoring never runs before compliance.** Every path to `scoring` passes through `compliance`.
- **The cycle is bounded.** `audit → clarify → scoring → audit` may repeat at most `MAX_CLARIFY_LOOPS = 2` rewrites; the visit after that routes to `manual_review`. The Critic is a language model and could object forever; the bound is what makes the graph halt. One counter, incremented in the clarify node, read in one transition function (`after_clarify`, using `>`, not `>=`, so the constant means what it says).
- **Retry only when it could help.** When the job has no parsed requirement lines, every retry would re-query the same text, so `after_audit` routes straight to `manual_review`.
- **Accepting and terminal are different claims.** `ACCEPTING = {audit}` (the Critic signed off); `TERMINAL = {rejected, manual_review}` (stopped early). Neither terminal state rejects the candidate; both mean a person should read the assessment.
- **`manual_review` drops the claims the Critic named** before showing the last draft, marked unverified.

### 3.3 Settling the verdicts

After the graph finishes (unless it ended in `rejected`), `_settle_verdicts` decides each requirement's final verdict:

1. **Quote check.** A `met` or `partial` must quote words actually present in its retrieved evidence, or it is not verified. Catches invented support.
2. **Contradiction check.** A `not_met` where the arithmetic half found a strongly matching résumé unit is sent back. Catches overlooked support, which step 1 cannot see.
3. **Verdict Auditor.** Reviews each verdict beside its own evidence.
4. **Degree rule.** A degree requirement that the résumé's own degree meets or exceeds, in a field it names, is set to met by code, quoting the education entry, and never lowered. A degree at the level whose field only overlaps is sent back to the model.
5. **Second reading.** Every remaining `not_met` is read again.
6. **One re-check call** for everything sent back by steps 2 to 5. Its answers pass the quote check again, so a second reading can find support but never invent it. A re-checked `not_met` that the numbers still contradict stays unverified and is marked disputed, so HR sees it rather than trusting it.

This runs whether or not the Critic signed off the written assessment.

## 4. Constants and where they came from

| Constant | Value | Meaning | Provenance |
|---|---|---|---|
| `_SEMANTIC_WEIGHT` | 0.6 | Semantic share of the arithmetic half | Design choice: conceptual matches matter more than wording |
| `_SEMANTIC_COSINE_FLOOR`, `_CEILING` | 0.30, 0.50 | Cosine stretched onto 0 to 100 | Measured on requirement/résumé-unit pairs, the comparison the score makes, over the 163 labelled requirements of `scripts/eval/skill_matching_set.json` (`scripts/calibrate_semantic_anchors.py`, 29 Oct 2026). Best cosine, median (p25 to p75): met 0.454 (0.379 to 0.577), partly met 0.481 (0.435 to 0.557), not met 0.341 (0.299 to 0.379). The floor sits at the not-met p25, the ceiling a little above the met median, so a typical met requirement scores about 77 and a typical not-met one about 20 (0.20 and 0.70, measured on whole documents, gave 51 and 28). Met and partly met are not told apart by cosine; the verdicts do that. The labels are drafts until HR reviews them. The migration `f7d2a9c4e815` keeps its own copy, so changing them affects new scores only. |
| `_COVERAGE_WEIGHT` | 0.5 | Coverage share of the match | Agreed 11 Oct 2026 |
| `_VERDICT_POINTS` | met 1, partial 0.5, not met 0 | Coverage points | Design choice |
| `MATCH_FLAG_THRESHOLD` | 60 | Below it, the application is flagged | In place since September 2026; the only flag reason since 19 Oct 2026 |
| `_RETRIEVAL_TOP_K` | 3 | Evidence chunks per requirement | Design choice |
| RRF constant | 60 | Rank damping in fusion | The standard RRF constant |
| `_BM25_K1`, `_BM25_B` | 1.5, 0.75 | BM25 term saturation and length normalisation | rank_bm25's defaults |
| `MAX_CLARIFY_LOOPS` | 2 | Rewrites the Critic may request | One rewrite with wider retrieval fixes the common case; a second covers an objection to the prose rather than the evidence; a third objection means the support is not there, which is a person's call |
| `_SUGGESTION_LIMIT` | 3 | Other openings suggested | Design choice |

Changing any of these, a prompt, or the order of the graph is an algorithm change, not a clean-up: it needs its own reason, a run of `eval_skill_matching.py`, and, for prompts, a re-recorded AI lock file reviewed with the change.

## 5. History

| Version | Date | What changed | Why |
|---|---|---|---|
| v1 | before Oct 2026 | Whole-résumé cosine plus BM25 normalised across every open job | |
| `applied_job_v2` | 11 Oct 2026 | Score measures the applied-to job only: arithmetic per requirement, plus verified requirement coverage, 50/50 | Under v1 the same résumé scored differently depending on what else was posted, and a résumé on the right topic scored near 100 however many requirements it missed |
| `applied_job_v3` | 18 Oct 2026 | Same formula. Degree and plural folding in the keyword half; section evidence for degree and credential requirements; role context and the reading rule for every judging agent; `basis` and reasoning on each verdict; per-requirement scores stored for HR; Lucene idf in BM25; every `not_met` read twice | v2 was too strict: a Master of Education major in Computer Science Teaching, applying to teach Computer Science, was judged against "Master's degree in Computer Science" as if unrelated (the model read "X, Y, or a related field" as all-of). In application 2438 the top three snippets for "Bachelor's degree" held no education entry at all. The measured v2 misses were all single readings of three snippets, e.g. "Google for Education Certified Trainer" judged no evidence of knowing educational technology. |
| | 19 Oct 2026 | Only a score below 60 flags an application; an unverified assessment no longer does (it used to flag as `unverified_assessment`) | Candidates scoring well above 60 were held for review because a model could not verify its own prose |
| | 22 Oct 2026 | Suggestions limited to openings the applicant can still apply to | |
| `applied_job_v4` | 29 Oct 2026 | Same formula. Semantic anchors 0.20/0.70 → 0.30/0.50, re-measured on requirement/unit pairs | The old anchors came from whole-document cosines, so a met requirement's semantic score sat around 51 and text similarity ran low for every candidate |

The retrieval graph replaced a single model call with the seven-agent automaton in September 2026; the retrieval strategy itself (BM25 + embeddings + RRF) did not change. Before that, the model was handed the whole résumé and job description regardless of relevance.

**Performance.** The embedding and chat clients are created once per process, not per request: each construction opened its own connection pool, so every request paid a fresh TLS handshake (9.88 s cold against 4.35 s warm in the NFR-01 measurement).
