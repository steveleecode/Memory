export type StatusPillProps = {
  label: string;
  tone?: "neutral" | "positive" | "warning";
};

export function StatusPill({ label, tone = "neutral" }: StatusPillProps) {
  return <span className={`memory-status-pill memory-status-pill--${tone}`}>{label}</span>;
}
