/**
 * The small presentational pieces the Candidate Profile and its tab bodies
 * both use. They lived at the bottom of CandidateProfilePage.tsx; once the
 * tabs moved into their own files these became shared, so they moved too
 * rather than being duplicated or imported back out of a page component.
 */

export function DetailRow({ value }: { value: string }) {
  if (!value) return null;
  return (
    <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-900)" }}>{value}</span>
  );
}

export function Pending() {
  return (
    <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-400)", fontStyle: "italic", fontSize: "var(--text-base)", marginTop: 8 }}>
      Not yet available.
    </p>
  );
}

/** Distinct from Pending() — the analysis ran, it just genuinely found
 * none (e.g. a resume with zero relevant strengths for this specific
 * role). Different from "hasn't been computed yet." */
export function NoneFound() {
  return (
    <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-400)", fontStyle: "italic", fontSize: "var(--text-base)", marginTop: 8 }}>
      None identified.
    </p>
  );
}
