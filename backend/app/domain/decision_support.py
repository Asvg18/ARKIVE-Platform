"""Decision Support's scoring functions, transcribed exactly from the
thesis (pp. 86-91). Pure.
"""

from __future__ import annotations


def compute_weighted_consensus(hr_score: float, dept_score: float, vp_score: float) -> float:
    """Algorithm 04, p.87: FinalScore = (W_hr*S_hr) + (W_dept*S_dept) +
    (W_vp*S_vp), institutional weights 0.30/0.30/0.40. Generic over input
    scale -- used both for the 1-5-scale executive consensus and,
    separately, for aggregating 0-100-scale rubric_coverage_score across
    the same three roles."""
    w_hr, w_dept, w_vp = 0.30, 0.30, 0.40
    return round((hr_score * w_hr) + (dept_score * w_dept) + (vp_score * w_vp), 2)


def compute_percentile_rank(score: float, all_scores: list[float]) -> float:
    """Algorithm 03, p.86: PR = (CF + 0.5*F) / N * 100, where CF is the
    count of scores strictly below `score`, F is the count tied with it
    (including itself), and N is the total count. `all_scores` must
    include `score` itself among the values being ranked."""
    below = sum(1 for s in all_scores if s < score)
    tied = sum(1 for s in all_scores if s == score)
    return round((below + 0.5 * tied) / len(all_scores) * 100, 1)


# the WSM weights exactly as written in the thesis (p.91); do not
# "rebalance" them. Named so synthesis.py displays the same constants
W_SKILL = 0.569
W_EXAM = 0.037
W_EVALUATOR_CHAIN = 0.043
W_RUBRIC = 0.351

# The executive consensus is computed on the scorecard's native 1-5
# scale, but the WSM assumes every criterion is normalized 0-100 — so
# callers multiply by this before feeding C3 in.
EXECUTIVE_CONSENSUS_SCALE = 20


def compute_final_synthesis_score(
    skill_score: float, exam_percentile: float, executive_consensus_score: float, interview_rubric_score: float
) -> float:
    """5.1.2.8, p.91: Weighted Sum Model A = sum(Ci*Wi) across four
    criteria, all normalized 0-100 — C1 skill match (w_skill=0.569), C2
    exam percentile (w_exam=0.037), C3 executive consensus
    (w_evaluator_chain=0.043), C4 interview rubric (w_rubric=0.351)."""
    w_skill, w_exam, w_evaluator_chain, w_rubric = W_SKILL, W_EXAM, W_EVALUATOR_CHAIN, W_RUBRIC
    final_score = (
        (skill_score * w_skill)
        + (exam_percentile * w_exam)
        + (executive_consensus_score * w_evaluator_chain)
        + (interview_rubric_score * w_rubric)
    )
    return round(final_score, 2)
