"""Settling the Scoring Agent's requirement verdicts after the retrieval
automaton halts (_settle_verdicts): the quote check, the contradiction
check, the Verdict Auditor, the degree rule and the re-check.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.schemas.skill_match import RequirementCheck, SkillMatchAnalysis

if TYPE_CHECKING:
    from app.services.rag_pipeline import RAGState


_NON_WORD_RE = re.compile(r"[^0-9a-z\[\]]+")


def _normalized(text: str) -> str:
    """Lower case, punctuation and runs of whitespace folded to one space
    -- so a quote that differs from its evidence only in a comma or a line
    break still matches, and one that differs in any word does not."""
    return _NON_WORD_RE.sub(" ", text.lower()).strip()


_QUOTE_STOPWORDS = {"a", "an", "and", "the", "of", "in", "to", "for", "with", "on", "at", "by", "or", "as", "is"}


def _quote_holds(quote: str, evidence: str) -> bool:
    """Whether a quote is really in the evidence: word for word, or made
    only of words the evidence contains (a skills list split across two
    chunks still holds). Any word the evidence lacks fails it, which is
    what stops invented support."""
    if len(quote) < 3:
        return False
    if quote in evidence:
        return True
    words = [w for w in quote.split() if len(w) > 1 and w not in _QUOTE_STOPWORDS]
    available = set(evidence.split())
    return len(words) >= 2 and all(word in available for word in words)


def _verified_checks(state: RAGState, drafts: list[RequirementCheck]) -> list[RequirementCheck]:
    """One check per requirement, in order, verified only if its quote is
    really in that requirement's retrieved evidence. The model picks the
    verdict; whether its evidence exists is decided here, by string
    comparison. A `met` on a missing quote counts for nothing; a skipped
    requirement is `not_met`."""
    evidence_by_requirement = {
        pair["requirement"]: " ".join(_normalized(item) for item in pair.get("evidence", []))
        for pair in state.get("evidence", [])
    }
    by_requirement = {draft.requirement.strip(): draft for draft in drafts}
    checks: list[RequirementCheck] = []
    for requirement in state.get("requirements") or []:
        draft = by_requirement.get(requirement.strip())
        if draft is None:
            checks.append(RequirementCheck(requirement=requirement, verdict="not_met", evidence_quote=""))
            continue
        quoted_in_evidence = _quote_holds(
            _normalized(draft.evidence_quote), evidence_by_requirement.get(requirement, "")
        )
        checks.append(
            RequirementCheck(
                requirement=requirement,
                verdict=draft.verdict,
                evidence_quote=draft.evidence_quote,
                basis=draft.basis,
                reasoning=draft.reasoning,
                # a not_met needs no evidence to stand; a met or partial does
                verified=draft.verdict == "not_met" or quoted_in_evidence,
            )
        )
    return checks


#: A not_met where the arithmetic half matched this strongly (calibrated
#: cosine of the closest resume unit, 0-100; 75 is about 0.58) is sent for
#: a second look. It only triggers a re-check, never sets a verdict.
_CONTRADICTION_SEMANTIC = 75.0


#: The reason given for the routine second reading of every not_met. Not
#: an objection: a confirmed not_met carries no note, and a skipped one is
#: left as it was rather than marked disputed.
_ROUTINE_RECHECK = "Judged not met on the first reading; every not met is read a second time against the whole resume."


_DEGREE_LEVELS = {"bachelor": 1, "master": 2, "doctorate": 3}


# words that say nothing about a degree's field
_FIELD_STOPWORDS = {
    "degree", "in", "of", "or", "and", "a", "an", "the", "field", "related", "relevant", "allied",
    "science", "arts", "redacted", "year", "with", "major", "specialization", "any", "equivalent",
    "preferably", "required", "holder", "graduate", "from", "accredited", "university", "college",
    *_DEGREE_LEVELS,
}


def _degree_level(tokens: list[str]) -> int:
    return max((_DEGREE_LEVELS[t] for t in tokens if t in _DEGREE_LEVELS), default=0)


_LEVEL_NAMES = {1: "bachelor's", 2: "master's", 3: "doctorate"}


# where a requirement's field list starts: "... degree in X", "Bachelor of X"
_FIELD_START_RE = re.compile(r"\b(?:in|of)\b\s+(.*)$", re.IGNORECASE)


# one named field from another: "X, Y, or a related field"
_FIELD_SPLIT_RE = re.compile(r",|;|/|\bor\b|\band/or\b", re.IGNORECASE)


# a field alternative that names no field of its own
_OPEN_ALTERNATIVE_RE = re.compile(r"\b(related|relevant|allied|equivalent|similar|any)\b", re.IGNORECASE)


def _named_fields(requirement: str) -> list[set[str]]:
    """The fields a degree requirement names, each as its words:
    "Master's degree in Computer Science, Education, or a related field"
    -> [{computer, science}, {education}]. "a related field" names none,
    so it is dropped -- whether a field is related is the model's call."""
    from app.services.skill_matching import _tokenize

    match = _FIELD_START_RE.search(requirement)
    if not match:
        return []
    fields = []
    for part in _FIELD_SPLIT_RE.split(match.group(1)):
        if _OPEN_ALTERNATIVE_RE.search(part):
            continue
        words = {t for t in _tokenize(part) if t not in _FIELD_STOPWORDS - {"science", "arts"} and len(t) > 1}
        if words:
            fields.append(words)
    return fields


def _degree_finding(requirement: str, state: RAGState) -> tuple[str, bool] | None:
    """The resume's education entry holding a degree at or above the
    level a requirement asks for, and whether it settles the requirement
    by rule -- or None.

    Settles it (True) when the degree's field contains every word of a
    field the requirement names, or the requirement names none: a Master
    of Education in Computer Science Teaching meets "Master's degree in
    Computer Science" and "Bachelor's degree in Computer Science". This is
    a rule, so the model's verdict cannot waver on it.

    Only overlaps (False) -- Computer Engineering shares a word with
    Computer Science -- is left to the model, as a reason to re-check."""
    from app.services.skill_matching import _tokenize

    required = _tokenize(requirement)
    level = _degree_level(required)
    if not level:
        return None
    named = _named_fields(requirement)
    overlap_words = set().union(*named) - {"science", "arts"} if named else set()
    chunks = state.get("redacted_chunks") or []
    sections = state.get("chunk_sections") or []
    partial: str | None = None
    for chunk, section in zip(chunks, sections):
        if section != "education":
            continue
        held = set(_tokenize(chunk))
        if _degree_level(list(held)) < level:
            continue
        if not named or any(field <= held for field in named):
            return chunk, True
        if partial is None and overlap_words & held:
            partial = chunk
    return (partial, False) if partial else None


def _degree_rule_check(requirement: str, chunk: str) -> RequirementCheck:
    """The verdict the degree rule sets: met, quoting the education entry
    (which _ensure_section_evidence put in this requirement's evidence),
    with the rule written out for HR."""
    from app.services.skill_matching import _tokenize

    level = _LEVEL_NAMES[_degree_level(_tokenize(requirement))]
    degree = chunk.replace(", [REDACTED]", "").replace("[REDACTED]", "").strip(" ,")
    return RequirementCheck(
        requirement=requirement,
        verdict="met",
        evidence_quote=chunk,
        basis="equivalent",
        reasoning=(
            f"Holds {degree}: a {level} degree or higher, in a field that includes the one this requirement names."
        ),
        verified=True,
        note="Met by the degree rule: a degree at or above the level asked for, in the named field, meets it.",
    )


def _settle_verdicts(
    state: RAGState, ctx: dict[str, Any], requirement_signals: dict[str, float]
) -> tuple[list[RequirementCheck], int, int]:
    """Every requirement's final verdict, and how many were objected to
    and re-checked.

    1. The quote check (_verified_checks): a met/partial must quote its
       evidence. Catches invented support -- false positives.
    2. The contradiction check: a not_met where the arithmetic half found
       a strongly matching resume unit. Catches overlooked support --
       false negatives, which step 1 cannot see, since a not_met quotes
       nothing.
    3. The Verdict Auditor, on the verdicts alone, each beside its own
       evidence (rag_catalog.VerdictAuditAgent).
    4. The degree rule (_degree_finding): a degree requirement the
       resume's own degree is at or above, in a field it names, is met --
       set by code, quoting the education entry, never lowered. A degree
       at or above the level whose field only overlaps the one named is
       sent back for the model to decide.
    5. Every remaining not_met, as a routine second reading: one reading
       of three snippets is the commonest way a real match is missed.
    6. One re-check call for everything 2-5 sent back; its answers go
       through the quote check again, so a second reading can find
       support but never invent it. A re-checked not_met that the
       numbers still contradict stays unverified and is marked disputed,
       so HR sees it rather than trusting it.

    Independent of whether the Critic signed off the prose."""
    from app.services.agents.rag_catalog import VERDICT_AUDIT, VERDICT_RECHECK

    analysis = SkillMatchAnalysis(**state["analysis"])
    checks = _verified_checks(state, analysis.requirement_checks)
    evidence_by_requirement = {pair["requirement"]: pair.get("evidence", []) for pair in state.get("evidence", [])}

    def contradicted(check: RequirementCheck) -> bool:
        return check.verdict == "not_met" and requirement_signals.get(check.requirement, 0.0) >= _CONTRADICTION_SEMANTIC

    reasons: dict[str, str] = {
        check.requirement: (
            "The résumé has text that closely matches this requirement, but the verdict was not_met."
        )
        for check in checks
        if contradicted(check)
    }
    objections = VERDICT_AUDIT.run(
        {"checks": [c.model_dump() for c in checks], "evidence_by_requirement": evidence_by_requirement}, ctx
    )["objections"]
    for requirement, objection in objections.items():
        reasons[requirement] = f"{reasons[requirement]} {objection}" if requirement in reasons else objection
    # the degree rule settles some outright (applied last, below); one that
    # only overlaps a named field is read again
    by_rule: dict[str, RequirementCheck] = {}
    for check in checks:
        # every verdict, a correct `met` included: in the eval set a met
        # the Auditor objected to was flipped by the re-check and lost
        finding = _degree_finding(check.requirement, state)
        if finding is None:
            continue
        degree, settled_by_rule = finding
        if settled_by_rule:
            by_rule[check.requirement] = _degree_rule_check(check.requirement, degree)
            reasons.pop(check.requirement, None)
            continue
        reason = (
            f"The resume lists \"{degree}\", a degree at or above the level this asks for, in a field that "
            "overlaps the one named; decide whether it is the same or a related field."
        )
        reasons[check.requirement] = f"{reasons[check.requirement]} {reason}" if check.requirement in reasons else reason
    # routine: re-read, but not a dispute -- see _ROUTINE_RECHECK
    routine = {
        c.requirement
        for c in checks
        if c.verdict == "not_met" and c.requirement not in reasons and c.requirement not in by_rule
    }
    for requirement in routine:
        reasons[requirement] = _ROUTINE_RECHECK

    if not reasons:
        return [by_rule.get(c.requirement, c) for c in checks], len(objections), 0

    disputed = [c for c in checks if c.requirement in reasons]
    # The second look sees the whole (blinded) resume, not just the top-k:
    # a dispute is often a case retrieval missed.
    whole_resume = state.get("redacted_chunks") or []
    full_evidence = {c.requirement: whole_resume for c in disputed}
    rechecked = VERDICT_RECHECK.run(
        {
            "checks": [c.model_dump() for c in disputed],
            "evidence_by_requirement": full_evidence,
            "reasons": reasons,
        },
        ctx,
    )["rechecked"]
    # the second look goes through the same quote check as the first,
    # against what it was shown
    second = {
        c.requirement: c
        for c in _verified_checks(
            {
                "requirements": [c.requirement for c in disputed],
                "evidence": [{"requirement": r, "evidence": items} for r, items in full_evidence.items()],
            },
            rechecked,
        )
    }
    settled: list[RequirementCheck] = []
    for check in checks:
        if check.requirement not in reasons:
            settled.append(by_rule.get(check.requirement, check))
            continue
        again = second[check.requirement]
        answered = again.requirement in {r.requirement for r in rechecked}
        if contradicted(again):
            again = again.model_copy(
                update={"verified": False, "note": "Disputed: judged not met twice, but the resume closely matches it. Check the resume."}
            )
        elif check.requirement in routine:
            # a second reading that agrees, or never answered, leaves the
            # first verdict as it was; one that changes it says so
            if answered and again.verdict != check.verdict:
                again = again.model_copy(update={"note": f"Re-checked: {_ROUTINE_RECHECK}"})
            else:
                again = check
        elif answered:
            again = again.model_copy(update={"note": f"Re-checked: {reasons[check.requirement]}"})
        else:
            # the re-check skipped it: the dispute stands, nothing counts
            again = check.model_copy(update={"verified": False, "note": f"Disputed: {reasons[check.requirement]}"})
        settled.append(again)
    return settled, len(objections), len(disputed)
