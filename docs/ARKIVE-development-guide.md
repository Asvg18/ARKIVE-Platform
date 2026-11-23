# ARKIVE — Development Guide & Build Strategy

*Written for solo development: you're the one building this system, with Claude as an ongoing technical co-developer — pairing session to session, not a multi-person team plan. Reflects the current, live scope, not the literal text of the original CCMS proposal, which has since been revised in a few places.*

> **Corrected 2026-08-30.** This guide was written before the build and described the plan; several parts had drifted from what was actually built and were being read as current truth. The claims about **pgvector**, **what LangGraph orchestrates**, and **Whisper voice interviews** have been corrected in place below, each with a short note saying what happened instead. Planning sections (§4's week-by-week, §11's checklist) keep their original wording as a record of the plan — only their factual claims are corrected. **`docs/ARKIVE-implementation-roadmap.md` is the authority on what exists**; when this file and the code disagree, the code wins and this file gets fixed.

---

## 1. Where things stand right now

- **What it is:** an HR recruitment + decision-support system, built for MSEUF Lucena's HR Dept but architected to be flexible/scalable beyond just MSEUF.
- **Actors (in the app itself):** Applicant, HR Administrator (merged HR Director + System Administrator — full pipeline authority and hire sign-off, *and* user/system management), Evaluator (covers both Department Head and VP — same role/portal, two people, different weights).
- **Headline contribution:** the multi-agent system (hybrid RAG+BM25 matching, LangGraph orchestration). DFA is still present but as a governance/safety layer, not the paper's centerpiece — "DFA-Governed" was dropped from the title, but a DFA still needs to be demonstrable at defense.
- **Exam stage:** scheduler only. No in-portal auto-grading — that was cancelled, and reconfirmed on realignment (see note below) despite the walkthrough spec's exam-auto-grading section.
- **Interviews:** sequential, face-to-face — HR Administrator → Department Head (Evaluator) → VP (Evaluator). **Built differently (FR-05, unresolved):** there is no voice recording and no Whisper transcription. Each round is captured as a structured HRD-F-APIEF scorecard plus written evaluator remarks, and the Interview Synthesis Agent grounds on those remarks instead of a transcript. Whether to build the voice stage or revise the thesis scope is **Decision A**, still open with the adviser.
- **Stack (as built):** React + Vite / FastAPI / LangChain (each agent's prompt + retrieval chain) + LangGraph 1.2.11 (a `StateGraph` orchestrating the AI Pre-Screening agents — **not** stage transitions; the DFA governs those) / Pydantic V2 / PostgreSQL 16 (**no pgvector** — see §10) / GPT-4o-mini + `text-embedding-3-small` / Figma for design / on-premises deployment. **OpenAI Whisper is not used** — see the interviews note above.
- **Timeline:** 2 months. **Team:** you, solo, developing it yourself.

Everything below builds on this. If any of it drifts from a future decision, this doc should get updated — don't let it go stale the way the original proposal did.

> **Realigned Aug 11, 2026** against `ARKIVE System Walkthrough and Functional Specification.md` (the finalized concept doc). Four decisions confirmed in that session: exam stays face-to-face/scheduler-only (not in-portal auto-graded), LangGraph orchestrates stage transitions while LangChain implements each agent's internal chain, the role model collapses from 4 roles to 3 (`hr_director` + `admin` → `hr_admin`), and the HR Director→Dept Head→VP weighted evaluator chain stays as locked. Full reasoning and the required code migration (Phase 1/2 already implemented the old 4-role split) are in `ARKIVE-realignment-plan.md` — read that before starting Week 3–4.

---

## 2. Reality check: solo, 2 months

I'll be as direct with you as I'd be with anyone I was pairing with: **solo, in 2 months, at full uniform polish across four portals, five agents, a hybrid retrieval system, a voice pipeline, a governance layer, and an on-prem deployment — that's not realistic, and I'd rather tell you now than have you find out in week 6.** This isn't me talking you out of it. It's me making sure the plan survives contact with reality.

Here's what actually changes with AI pairing, and what doesn't:

- **What compresses:** the typing. I can generate a Pydantic schema, a FastAPI route, and the React screen that consumes it in one sitting. Boilerplate, CRUD scaffolding, repetitive patterns across the four portals — I can move fast on all of that.
- **What doesn't compress:** your time. You still have to run it, test it, understand it well enough to defend it alone, catch the bugs I don't see, and make the judgment calls (how good is "good enough" on the matching score, what does the DFA error message actually need to say, whether a given screen is actually usable). There's no second person to catch what you miss — so testing as you go isn't optional, it's the only safety net you have.
- **What this means practically:** the leverage is real, but the schedule below is still tight. Treat the cut list in §13 as something you'll likely need, not a hedge that probably won't matter.

**Quality, redefined for this context: not "everything polished," but "the pieces you defend are bulletproof, and everything else is simple and honest."** The System Admin panel can be a plain CRUD screen. The DFA-blocked-transition demo and the hybrid matching score need to work every time, live, in front of your panel.

---

## 3. How we'll actually work together

No standups, no meetings — just sessions. The pattern that works best for solo-plus-AI development is **one thin vertical slice per session**: pick one real feature (e.g. "HR Director can create a job requisition"), and in that session we build the DB migration, the API endpoint, and the screen that uses it — together, end to end — rather than building a whole layer (all backend, or all frontend) before connecting anything. That way you're never holding a frontend that's guessing at an API, or a backend with no way to see if it actually works.

Concretely, each session looks like:
1. We name the one slice we're building.
2. I draft the schema/migration + endpoint + screen for it.
3. You run it locally, click through it, tell me what's broken or feels wrong.
4. We fix it before moving to the next slice.

This is also why the "define the contract early" idea from before still matters even solo — nailing down the shape of your core objects (User, JobRequisition, CandidateApplication, StageInstance, Interview) in the very first session means every slice after that fits together without rework.

---

## 4. The 2-month plan (8 weeks)

| Week | Focus | Exit criteria |
|---|---|---|
| 1 | Core schemas + DB + auth + all 4 portal shells with real navigation | You can log in as each of the 4 roles and see a real (if empty) dashboard |
| 2 | Manual, no-AI pipeline end-to-end, DFA-lite gate in place from the start | You can manually move a candidate applied → hired; illegal stage jumps are blocked |
| 3–4 | Skill Matching Agent (highest technical risk — give it the most room) | Résumé + job description in → match score + top skills out, explainable, not necessarily perfectly tuned |
| 5 | Evaluator chain + DFA gate over the consolidator | Three evaluators submit in sequence; skipping is blocked and demoable |
| 6 | Interview capture pipeline (audio → Whisper → synthesized summary) | Isolated on purpose — first candidate to simplify if you're behind, see §13 |
| 7 | Evaluation Consolidator + final decision + Document Compiler | Weighted scoring, auto-hire/compare logic, Pre-201 package on hire |
| 8 | Testing, bug fixing, defense rehearsal | Black-box pass on defense-critical flows, one full dry-run demo |

That's a full schedule with no slack — realistically, expect to start leaning on the cut list around week 5 or 6 unless week 1–4 go faster than planned. That's normal, not a sign anything's going wrong.

### Right now: Session 1

Since you want to start immediately, here's exactly what Session 1 should cover:
1. Repo layout: `/backend` (FastAPI), `/frontend` (React+Vite), `/db` (migrations, seed scripts)
2. Docker Compose for local PostgreSQL 16 *(the original plan enabled `pgvector` here; it was never adopted — see §10)*
3. Pydantic schemas for `User`, `JobRequisition`, `CandidateApplication`, `StageInstance` — this is the contract everything else builds on
4. DB migrations matching those schemas
5. Auth skeleton: JWT with `{user_id, role}`, one shared login route, role-based redirect
6. Bare shells for all 4 portal routes in React, wired to real auth (even if the dashboards are empty)

Say the word and we can start on this right now.

---

## 5. System architecture at a glance

```
                    ┌─────────────────────────────────────┐
                    │              Client Browser           │
                    │   React + Vite  (4 portal front-ends) │
                    └───────────────────┬───────────────────┘
                                        │ HTTPS (local network)
                    ┌───────────────────▼───────────────────┐
                    │         FastAPI Application Server      │
                    │  ┌─────────────┐  ┌──────────────────┐ │
                    │  │  Auth (JWT)  │  │  DFA-lite guard   │ │
                    │  └─────────────┘  └──────────────────┘ │
                    │  ┌─────────────────────────────────┐   │
                    │  │     LangGraph Orchestrator        │   │
                    │  │  Matching │ Screening │ Interview │   │
                    │  │  Synth. │ Eval Consolidator │ Doc  │   │
                    │  │              Compiler             │   │
                    │  └─────────────────────────────────┘   │
                    └───────────────────┬───────────────────┘
                                        │
                    ┌───────────────────▼───────────────────┐
                    │           PostgreSQL 16                 │
                    │   (shared candidate record, embeddings  │
                    │    as JSON, audit log, all app state)   │
                    └─────────────────────────────────────────┘
```

Everything reads and writes through the one FastAPI service and the one Postgres instance — no portal talks directly to the database, and no agent owns its own private data store. That single-source-of-truth rule is what makes the "no contradictory stage" guarantee actually hold.

---

## 6. Data model

This reconciles the thesis ERD with the configurability decision — job-specific workflows need a place to live, so `JobRequisition` gets a `workflow_definition` and candidates get a `StageInstance` per stage rather than one fixed set of columns.

- **User** — id, role (`applicant` / `hr_admin` / `evaluator`), evaluator_type (`dept_head` / `vp`, null otherwise), auth_provider, provisioning_source
- **JobRequisition** — id, title, department, status, `workflow_definition` (ordered JSON list of stage types this job uses)
- **CandidateApplication** — id, applicant_id, requisition_id, `current_stage`, created_at, updated_at
- **StageInstance** — id, application_id, stage_type, status (`pending` / `in_progress` / `complete` / `skipped`), stage-specific payload (JSON), completed_at
- **SkillMatch** — application_id, semantic_score, keyword_score, final_score (Sfinal), top_skills (JSON), computed_at
- **Examination** — application_id, scheduled_at, location, outcome (manual entry: pass/fail or score), recorded_by, recorded_at
- **Interview** — id, application_id, evaluator_id, evaluator_role (`hr_admin` / `dept_head` / `vp`), scheduled_at, transcript_url, synthesized_summary, score, submitted_at, locked (bool)
- **EvaluationConsolidation** — application_id, weighted_score, computed_at, decision_path (`auto_hire` / `compared` / `pending`)
- **Document** — id, application_id, type, file_url, uploaded_by, uploaded_at
- **StageHistory** — id, application_id, from_stage, to_stage, triggered_by (user_id or `system`), timestamp — this is your audit trail and your DFA's transition log in one table

A note from experience: resist the urge to add columns to `CandidateApplication` for "current interview score" or similar. Anything derivable from `Interview` or `StageInstance` should be computed, not duplicated — that duplication is exactly the bug pattern that caused the original mockup's contradictory-stage problem.

---

## 7. Role model & auth (application roles, not your dev team)

**Updated Aug 11, 2026 — realigned against the finalized functional spec; see `ARKIVE-realignment-plan.md`.** Three roles now, not four — `hr_director` and `admin` merge into a single `hr_admin` role. This requires a migration in the already-built Phase 1/2 code (role enum, seed data, `require_role()` checks) before Week 3–4 starts; not yet done as of this update.

Three roles, one login page, role read from the JWT and re-checked server-side on every request (never trust which screen rendered).

- **Applicant** — self-registers (institutional email or SSO)
- **HR Administrator** (`hr_admin`) — full pipeline access, sole hire/reject authority, *and* user/system management (invites Evaluator accounts, manages DB/security/algorithm thresholds). Merges the former separate `hr_director` and `admin` roles.
- **Evaluator** — scoped to interviews assigned to them; the same role covers Department Head and VP, distinguished by an `evaluator_type` field that determines their weight (30% vs 40%) and which sequence slot (S4 vs S5) they fill. (The finalized spec's broader evaluator examples — Faculty Panels, Hiring Committees, Academic Curators — are illustrative institutional titles, not new weighted sub-types; the two-slot dept_head/vp mechanism stays as locked.)

Two checks on every API request, both server-side:
1. **Route-level role check** — can this role touch this endpoint category at all?
2. **Resource-ownership check** — is this specific record theirs? (`WHERE evaluator_id = current_user.id`, not fetch-all-then-filter)

Return **404, not 403** when a record exists but isn't the requester's — don't confirm existence to someone who shouldn't know. Lock an `Interview` row after submission; edits go through a separate, logged "revise" action, not a raw update.

---

## 8. Configurable workflow model

- A stage type library: Document Upload, Skill Matching, Examination (scheduler-only), Interview (repeatable — HR Director / Dept Head / VP), Reference Check, Background Check, Final Decision, Onboarding.
- Each `JobRequisition` picks and orders stages from that library at creation time.
- Each `CandidateApplication` instantiates that job's specific sequence as `StageInstance` rows. The applicant stepper and HR pipeline view both render from that instance list — never a hardcoded global list.
- **Solo-timeline note:** the full drag-and-order Job Opening Builder UI is a good cut candidate (see §13) — the underlying data model and DFA generation logic is what matters academically, not necessarily a polished authoring interface for it.

---

## 9. DFA governance — my recommendation

Generate it per job, from that job's `workflow_definition`, rather than hand-maintaining one fixed shape. Reasons:

1. You've already committed to the system being flexible/scalable — a hand-written fixed automaton fights that the moment a job wants a different sequence.
2. It's genuinely less code, not more — a small generator function beats a manually maintained transition table.
3. It's still legitimate, demonstrable automata theory for your defense: "here's the generator, here's the automaton it builds for this job, here's what happens when something tries to violate it."

**What it needs to do — nothing more:** given a job's ordered stage list, build a table of valid transitions between consecutive stages, then reject (with a clear error, not a silent failure) any write that isn't the next valid stage. Resist scope creep — no parallel states, no general rules engine.

**Where to put the gate:**
- The screening → next-stage cutoff (pass/shortlist threshold)
- The evaluator chain: Evaluation Consolidator cannot run until HR Director + Dept Head + VP interview scores all exist — your best "caught a hallucinated skip" demo
- The final decision terminal gate: nothing can be marked `Hired` without the full evaluator chain complete

Everything else (résumé upload, exam scheduling) is naturally linear — don't force a gate onto a step that was never going to be skipped anyway.

---

## 10. Agent specs

Each agent's *internal* work (prompt composition, retrieval, output parsing) is a LangChain chain. (Realigned Aug 11, 2026 — see `ARKIVE-realignment-plan.md`; the original plan didn't name LangChain explicitly.)

**Corrected 2026-08-30 — the paragraph here previously said all five agents run as LangGraph nodes with LangGraph owning *when* each fires, triggered by `StageInstance` transitions. That is not what was built, and it matters at defense.** What exists ([app/services/orchestration.py](../backend/app/services/orchestration.py)) is a `StateGraph` over **AI Pre-Screening only** — three agents that run together in one request, with two conditional branches (does this job have pre-screening questions; does it have examination stages). Everything else is governed by the **DFA**, deliberately: the rest of the pipeline spans weeks and waits on human decisions, which a graph in a single request cannot model. The thesis title says "DFA-Governed" *and* "LangGraph"; both are literally true, each doing the job it suits.

LangGraph is also not an older or competing LangChain — `langchain==1.3.16` declares `langgraph>=1.2.11` as a hard dependency, and `langchain.agents.factory` imports `StateGraph` from it. One stack, not two.

**Matching Agent**
- Trigger: résumé + job description both present
- Does: computes `Sfinal = α·Ssemantic + (1−α)·Skeyword` — semantic score from cosine similarity over OpenAI `text-embedding-3-small` embeddings, keyword score from real BM25 (`rank_bm25`) over the résumé's reviewed form fields
- **The semantic score is calibrated, not raw cosine** (2026-09-24). A résumé and a job posting are different kinds of document, so their cosine never approaches 1.0 — measured on the dev data, unrelated pairs sit at 0.16–0.24 and the strongest real matches at 0.56–0.66. Used directly as a percentage, that capped every `Sfinal` in the high 70s, so the 80+ "strong match" band HR is shown was unreachable. `_semantic_score` now maps cosine 0.20–0.70 linearly onto 0–100, clamped at both ends; the raw cosine is stored beside it as `cosine_similarity`. Existing scores were converted by migration `f7d2a9c4e815`. Re-measure the anchors once there are more real résumés.
- **No pgvector, by deliberate choice** (recorded in handoff v1 §2.2, re-verified live 2026-08-30: `SELECT extname FROM pg_extension` returns only `plpgsql`, and no column anywhere has a vector type). Embeddings are **cached as plain JSON columns** — `job_requisitions.embedding` and `application_resumes.embedding`, computed once and reused — and the cosine similarity is computed **in Python**, not by the database. At this corpus size (~12 requisitions) an ANN index would buy nothing, and adding the extension would be a deployment dependency for no measurable gain. If the corpus ever grows into the thousands, that trade flips and pgvector becomes the right call.
- **Both halves score the reviewed form, not the uploaded PDF** (changed 2026-10-11). Semantic *and* BM25 read `_resume_scoring_text` — the structured fields the applicant reviewed and submitted (summary, experience, education, skills, certifications, other sections), without the name, contact block or dates. Until then they read `ApplicationResume.raw_extracted_text`, what pypdf recovered from the file, so an applicant's corrections on the review step never reached the score. The PDF text is now only the fallback when every field is blank. Cached résumé embeddings from the old source were cleared by migration `5b8e2d7c9f14`; scores already stored on applications were left as they were.
- BM25 doubles as a grounding check: if semantic score is high but BM25 finds no lexical support for a claimed skill, discount it — your defense against RAG hallucinating a skill match
- Output: `SkillMatch` row, top skills, feeds the HR Director's ranked view

**Screening Agent**
- Trigger: after matching
- Does: simple eligibility checks (required credentials present, no disqualifying flags) — deliberately a rules check, not an LLM call; keep it boring and reliable

**Interview Synthesizer**
- Trigger: an `Interview` row gets a transcript_url
- Does: Whisper transcribes, GPT-4o-mini turns the transcript into a structured summary (strengths, concerns, notable quotes) — a summarization call, not a scoring call
- Output: `synthesized_summary` on the `Interview` row

**Evaluation Consolidator**
- Trigger: gated by the DFA — only fires once all three `Interview.score` values exist for an application
- Does: weighted average (30/30/40), decides `auto_hire` vs `compared` per the VP's rating
- Output: `EvaluationConsolidation` row

**Document Compiler**
- Trigger: `Hired`
- Does: verifies required pre-employment docs are present, compiles the Pre-201 file package
- Output: `Document` rows tagged for the package, notification to the applicant for anything missing

---

## 11. Tech stack setup checklist

1. **Repo layout:** `/backend` (FastAPI), `/frontend` (React+Vite), `/db` (migrations, seed scripts)
2. **Postgres:** Docker Compose locally, matches your eventual on-prem target closely enough to avoid surprises. *(The plan said "+ pgvector"; it was never adopted — see §10 for why, and what embeddings use instead.)*
3. **FastAPI structure:** routers per portal (`/applicant`, `/hr`, `/evaluator`, `/admin`), a shared `dependencies.py` for the two-check auth pattern
4. **LangGraph:** *(planned as one graph per application lifecycle, nodes = the five agents. Built narrower — one graph over the AI Pre-Screening agents, with the DFA governing the multi-week lifecycle instead. See §10.)*
5. **Pydantic V2 models first, DB models second** — they're your contract, and catching a shape mismatch at the schema level beats catching it after something's already built on top of it
6. **Cost control:** during development, mock LLM/Whisper responses for anything you're not actively testing that specific call — only hit the real OpenAI API when you're testing that exact feature. Solo dev on a capstone budget shouldn't be paying to re-run the whole pipeline every time you touch an unrelated screen.

---

## 12. Testing & validation

- **Black-box test cases per requirement** — write these before building the corresponding feature, not after; it forces the acceptance criteria to be concrete, and it's the closest thing you have to a second pair of eyes when working solo
- **Specific cases worth having from week 1:** Evaluator hits an HR-only endpoint → 403; Evaluator requests an unassigned interview → 404; Evaluator resubmits a locked scorecard → 403; agent attempts to skip a DFA-gated transition → blocked with a clear error, state unchanged
- **ISO 25010 + UAT** with real MSEUF HR staff — these need outside people regardless of team size, so schedule them as early in week 8 as you can, not the day before defense

---

## 13. If a week runs long: cut in this order

Decided now, not in a panic later. Each of these can be simplified without gutting the thesis's actual contribution (matching + DFA-governed evaluator chain):

1. **Audio recording UI polish** — drop in-browser recording, accept an uploaded audio file instead. Whisper doesn't care how the audio arrived.
2. **Job Opening Builder authoring UI** — hardcode 1–2 demo job workflows in seed data instead of building a full drag-and-order interface. Keep the underlying per-job DFA generation working; simplify only the UI that authors it.
3. **Document Compiler / Pre-201 packaging** — simplify from an auto-compiled package to a manual checklist HR can tick off.
4. **System Admin portal** — least defense-critical surface. Bare functional CRUD is fine.
5. **On-prem deployment hardening** — get it running reliably for the demo; defer production-grade hardening notes to the write-up's "future work."
6. **Exam module niceties** — it's already scheduler-only; don't add anything beyond date/time/location and a manual outcome field.

Do **not** cut: the manual pipeline + DFA gate (Week 2), the Skill Matching Agent, or the evaluator chain (Week 5) — those three are the actual thesis contribution, and everything above exists to protect the time they need.

---

## 14. Decisions still needed

- **Algorithm 03 (exam percentile ranking):** now that the exam is scheduler-only, does this idea move into interview scoring, get dropped, or survive as an optional manual-entry feature? Worth resolving before Week 5.
- **DFA generation approach:** my recommendation is in §9 — still your call to confirm, and it affects how Week 2 gets built.
