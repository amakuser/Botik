import { motion, useReducedMotion } from "framer-motion";
import { cn } from "../../../shared/lib/utils";
import type { GlobalState } from "../../../shared/contracts";

export interface HealthRingProps {
  score: number;
  state: GlobalState;
  size?: number;
  className?: string;
  ariaLabel?: string;
}

const STROKE_COLOR: Record<GlobalState, string> = {
  healthy: "rgb(var(--token-green))",
  warning: "rgb(var(--token-amber))",
  critical: "rgb(var(--token-red))",
};

const TEXT_COLOR: Record<GlobalState, string> = {
  healthy: "rgb(var(--token-green))",
  warning: "rgb(var(--token-amber))",
  critical: "rgb(var(--token-red))",
};

function pickStateForScore(score: number): GlobalState {
  if (score < 50) return "critical";
  if (score < 80) return "warning";
  return "healthy";
}

export function HealthRing({
  score,
  state,
  size = 64,
  className,
  ariaLabel,
}: HealthRingProps) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.max(0, Math.min(100, score));
  const ringState: GlobalState = state ?? pickStateForScore(clamped);
  const strokeWidth = Math.max(4, Math.round(size * 0.1));
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const ratio = clamped / 100;

  return (
    <div
      data-ui-role="health-ring"
      data-ui-state={ringState}
      data-ui-score={clamped}
      role="img"
      aria-label={ariaLabel ?? `Health score ${clamped}, state ${ringState}`}
      className={cn(
        "relative inline-flex items-center justify-center",
        ringState === "critical"
          ? "motion-safe:animate-[pulse_1s_ease-in-out_infinite]"
          : null,
        className,
      )}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="rgb(var(--token-text-muted) / 0.2)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={STROKE_COLOR[ringState]}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          transform={`rotate(-90 ${center} ${center})`}
          initial={false}
          animate={{ pathLength: ratio }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : { duration: 0.6, ease: [0.0, 0.0, 0.2, 1] }
          }
          style={{ pathLength: ratio }}
        />
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center"
        style={{ color: TEXT_COLOR[ringState] }}
      >
        <span
          className="text-base font-semibold tabular-nums leading-none"
          data-testid="home.hero.score"
        >
          {clamped}
        </span>
      </div>
    </div>
  );
}
