import { cn } from "../../../shared/lib/utils";

export type StatusDotState = "ok" | "warning" | "critical" | "unknown" | "info";
export type StatusDotSize = "sm" | "md" | "lg";

export interface StatusDotProps {
  state: StatusDotState;
  size?: StatusDotSize;
  className?: string;
  pulse?: boolean;
  ariaLabel?: string;
}

const STATE_CLASS: Record<StatusDotState, string> = {
  ok: "bg-[rgb(var(--token-green))]",
  warning: "bg-[rgb(var(--token-amber))]",
  critical: "bg-[rgb(var(--token-red))]",
  unknown: "bg-[rgb(var(--token-text-muted))]",
  info: "bg-[rgb(var(--token-accent))]",
};

const SIZE_CLASS: Record<StatusDotSize, string> = {
  sm: "h-1.5 w-1.5",
  md: "h-2.5 w-2.5",
  lg: "h-3.5 w-3.5",
};

export function StatusDot({
  state,
  size = "md",
  className,
  pulse = false,
  ariaLabel,
}: StatusDotProps) {
  return (
    <span
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      data-ui-role="status-dot"
      data-ui-state={state}
      className={cn(
        "inline-block rounded-full",
        SIZE_CLASS[size],
        STATE_CLASS[state],
        pulse ? "motion-safe:animate-pulse" : null,
        className,
      )}
    />
  );
}
