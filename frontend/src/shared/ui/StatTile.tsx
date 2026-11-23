import type { ReactNode } from "react";
import { Card } from "./Card";

export function StatTile({
  icon,
  label,
  value,
  badge,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  badge?: ReactNode;
}) {
  return (
    <Card padding={20}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "var(--radius)",
            background: "var(--accent-bg)",
            color: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
        {badge}
      </div>
      <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-2xl)", fontWeight: 700, color: "var(--ink-900)" }}>
        {value}
      </div>
    </Card>
  );
}
