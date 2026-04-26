import { motion } from "framer-motion";
import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type {
  ActivityEntry,
  ActivitySeverity,
} from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";

export interface ActivityCardProps {
  activity: ActivityEntry[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

function severityLabel(severity: ActivitySeverity): string {
  switch (severity) {
    case "info":
      return "Инфо";
    case "warn":
      return "Предупр.";
    case "err":
      return "Ошибка";
    case "critical":
      return "Критично";
    default:
      return severity;
  }
}

function formatTime(iso: string): string {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  return new Date(parsed).toISOString().slice(11, 19) + "Z";
}

const SEVERITY_COLOR: Record<ActivitySeverity, string> = {
  info: "text-[rgb(var(--token-text-primary))]",
  warn: "text-[rgb(var(--token-amber))]",
  err: "text-[rgb(var(--token-red))]",
  critical: "text-[rgb(var(--token-red))]",
};

export function ActivityCard({
  activity,
  isLoading,
  isError,
  onRetry,
}: ActivityCardProps) {
  if (isError) {
    return (
      <article
        data-ui-role="activity-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Активность
        </h3>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось загрузить список задач.
        </p>
        <Button variant="ghost" size="sm" onClick={onRetry}>
          Повторить
        </Button>
      </article>
    );
  }

  if (isLoading) {
    return (
      <article
        data-ui-role="activity-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="activity-card" width="40%" height="0.9rem" />
        <SkeletonBox scope="activity-card" width="100%" height="0.8rem" />
        <SkeletonBox scope="activity-card" width="100%" height="0.8rem" />
        <SkeletonBox scope="activity-card" width="100%" height="0.8rem" />
      </article>
    );
  }

  if (activity.length === 0) {
    return (
      <article
        data-ui-role="activity-card"
        data-ui-scope="home"
        data-ui-state="empty"
        className={cn(
          "panel rounded-xl border p-4 flex flex-col gap-2",
          "border-white/10",
        )}
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Активность
        </h3>
        <p className="text-sm text-[rgb(var(--token-text-secondary))]">
          Тихо. Последние события недоступны.
        </p>
      </article>
    );
  }

  const entries = activity.slice(0, 5);

  return (
    <article
      data-ui-role="activity-card"
      data-ui-scope="home"
      data-ui-state="populated"
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-2",
        "border-white/10",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Активность
        </h3>
        <span className="text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))]">
          последние {entries.length}
        </span>
      </header>
      <ul className="flex flex-col gap-1">
        {entries.map((entry, idx) => (
          <motion.li
            key={`${entry.ts}-${idx}`}
            data-ui-role="activity-entry"
            data-ui-state={entry.severity}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: [0.0, 0.0, 0.2, 1] }}
            className="flex items-baseline justify-between gap-3 text-xs"
          >
            <span
              className={cn(
                "truncate font-medium",
                SEVERITY_COLOR[entry.severity],
              )}
            >
              {entry.summary}
            </span>
            <span className="text-[rgb(var(--token-text-secondary))]">
              {severityLabel(entry.severity)}
            </span>
            <span className="text-[rgb(var(--token-text-muted))] tabular-nums">
              {formatTime(entry.ts)}
            </span>
          </motion.li>
        ))}
      </ul>
    </article>
  );
}
