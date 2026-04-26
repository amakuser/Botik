import { cn } from "../../../shared/lib/utils";

export type ProtectionChipState =
  | "protected"
  | "attention"
  | "unprotected"
  | "failed"
  | "pending"
  | "unknown";

export interface ProtectionChipProps {
  state: ProtectionChipState;
  count: number;
  label: string;
  className?: string;
}

const CHIP_CLASS: Record<ProtectionChipState, string> = {
  protected:
    "bg-[rgb(var(--token-green)/0.12)] text-[rgb(var(--token-green))] border-[rgb(var(--token-green)/0.32)]",
  attention:
    "bg-[rgb(var(--token-amber)/0.12)] text-[rgb(var(--token-amber))] border-[rgb(var(--token-amber)/0.32)]",
  unprotected:
    "bg-[rgb(var(--token-red)/0.14)] text-[rgb(var(--token-red))] border-[rgb(var(--token-red)/0.4)]",
  failed:
    "bg-[rgb(var(--token-red)/0.18)] text-[rgb(var(--token-red))] border-[rgb(var(--token-red)/0.5)]",
  pending:
    "bg-[rgb(var(--token-amber)/0.1)] text-[rgb(var(--token-amber))] border-[rgb(var(--token-amber)/0.28)]",
  unknown:
    "bg-white/5 text-[rgb(var(--token-text-muted))] border-white/10",
};

export function ProtectionChip({
  state,
  count,
  label,
  className,
}: ProtectionChipProps) {
  return (
    <span
      data-ui-role="protection-chip"
      data-ui-state={state}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs",
        "tabular-nums font-medium",
        CHIP_CLASS[state],
        className,
      )}
    >
      <span className="font-semibold">{count}</span>
      <span className="text-[0.7rem] uppercase tracking-wide opacity-80">{label}</span>
    </span>
  );
}
