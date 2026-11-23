import type { ReactNode } from "react";
import { ChevronDownIcon } from "../../../../../shared/ui/icons";

/** A select that says what it filters: "Department  All ▾". */
export function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="ark-filter">
      <span className="ark-filter__label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
      <ChevronDownIcon width={14} height={14} className="ark-filter__caret" aria-hidden="true" />
    </label>
  );
}
