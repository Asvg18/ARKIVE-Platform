/**
 * The Candidate Synthesis as one stacked record, for the Pre-201 package;
 * the Candidate Profile lays the same sections out in two columns.
 */

import type { CandidateSynthesis } from "../../../../shared/api/pipeline";
import { SynthesisVerdict } from "./synthesis/SynthesisVerdict";
import { SynthesisBrief } from "./synthesis/SynthesisBrief";
import { SynthesisAgreement, SynthesisAspects } from "./synthesis/SynthesisAspects";
import { SynthesisEvidence } from "./synthesis/SynthesisEvidence";
import { SynthesisActivity } from "./synthesis/SynthesisActivity";

/** The whole synthesis as one stacked record: the verdict in the form's
 * own words, the justification, then the evidence (the rubric by area,
 * where the evaluators agreed, what the earlier stages found), and the
 * agent log as the audit trail. `expanded` opens every section, because a
 * hired applicant's permanent record hides nothing.
 *
 * No overall score or criterion breakdown is shown: the HR Director's
 * office could not confirm how the final assessment is computed. The
 * criteria still arrive on `synthesis.criteria`, and the verdict reads
 * them. */
export function SynthesisPanel({
  synthesis,
  expanded = false,
}: {
  synthesis: CandidateSynthesis;
  expanded?: boolean;
}) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <SynthesisVerdict synthesis={synthesis} expanded={expanded} />
      <SynthesisBrief synthesis={synthesis} expanded={expanded} />
      <SynthesisAspects aspects={synthesis.aspects} />
      <SynthesisAgreement agreement={synthesis.agreement} />
      <SynthesisEvidence evidence={synthesis.evidence} expanded={expanded} />
      <SynthesisActivity agents={synthesis.agents} agentTrail={synthesis.agent_trail} open={expanded} />
    </div>
  );
}
