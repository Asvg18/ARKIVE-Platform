export function ProgressBar({
  value,
  max = 100,
  color = "var(--accent)",
}: {
  value: number;
  max?: number;
  color?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      style={{
        height: 4,
        borderRadius: "var(--radius-full)",
        background: "var(--surface-bg-alt)",
        overflow: "hidden",
      }}
    >
      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: "var(--radius-full)" }} />
    </div>
  );
}
