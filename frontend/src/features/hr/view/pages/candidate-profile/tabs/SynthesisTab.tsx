/**
 * The Synthesis tab, the profile's default: the evidence half of the
 * page, read top to bottom as the case for the verdict beside it.
 */

import { SynthesisActivity } from "../../../components/synthesis/SynthesisActivity";
import { SynthesisAgreement, SynthesisAspects } from "../../../components/synthesis/SynthesisAspects";
import { SynthesisBrief } from "../../../components/synthesis/SynthesisBrief";
import {
  ClampedText,
  SynthesisEvidence,
  type EvidenceSource,
  type EvidenceView,
} from "../../../components/synthesis/SynthesisEvidence";
import type { CandidateProfile } from "../../../../../../shared/api/pipeline";

interface SynthesisTabProps {
  profile: CandidateProfile;
  /** Which of the resume read's lists is showing — held on the page. */
  evidenceView: EvidenceView;
  onEvidenceViewChange: (view: EvidenceView) => void;
  /** Through to the tab holding an evidence figure's source record. */
  onOpenSource: (source: EvidenceSource) => void;
}

/** The case for the verdict in the left-hand column (../CandidateSidebar),
 * in order: the recommendation with its facts folded away, each
 * interviewer's conclusion, the rubric by area, the earlier stages'
 * figures and the resume read (with Top Skills beside it), the
 * candidate's letter, and the agent log, shut until asked for. State
 * stays on the page (see ../types.ts). */
export function SynthesisTab({ profile, evidenceView, onEvidenceViewChange, onOpenSource }: SynthesisTabProps) {
  const synthesis = profile.synthesis;
  const hasInterviews = synthesis.aspects.length > 0 || synthesis.agreement.rounds.length > 0;
  const hasEvidence = synthesis.evidence.match_score != null || synthesis.evidence.exam_score != null;
  const hasBrief = synthesis.brief != null || synthesis.fact_sheet.length > 1;

  return (
    <div style={{ display: "grid", gap: 20 }}>
      {!hasBrief && !hasInterviews && !hasEvidence && (
        <div className="ark-panel">
          <div className="ark-empty">
            <span className="ark-empty__title">Nothing to weigh yet</span>
            <span className="ark-empty__body">
              This fills in as {profile.applicant_name.split(" ")[0]} moves through pre-screening, examinations and
              interviews.
            </span>
          </div>
        </div>
      )}

      <SynthesisBrief synthesis={synthesis} />

      <SynthesisAgreement agreement={synthesis.agreement} />
      <SynthesisAspects aspects={synthesis.aspects} />

      <SynthesisEvidence
        evidence={synthesis.evidence}
        topSkills={profile.top_skills}
        view={evidenceView}
        onViewChange={onEvidenceViewChange}
        onOpenSource={onOpenSource}
      />

      {profile.letter_of_intent && (
        <section className="ark-panel" aria-labelledby="letter-heading">
          <div className="ark-panel__head">
            <h2 id="letter-heading" className="ark-panel__title">
              Letter of intent
            </h2>
          </div>
          <div className="ark-panel__body">
            <ClampedText text={profile.letter_of_intent} lines={3} label="letter" />
          </div>
        </section>
      )}

      <SynthesisActivity agents={synthesis.agents} agentTrail={synthesis.agent_trail} open={false} />
    </div>
  );
}
