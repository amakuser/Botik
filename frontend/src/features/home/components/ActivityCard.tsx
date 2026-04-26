import { motion } from "framer-motion";
import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { JobSummary } from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";

export interface ActivityCardProps {
  jobs: JobSummary[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

type EntryState = "info" | "warn" | "err" | "critical";

function classifyJobState(state: string): EntryState {
  switch (state) {
    case "failed":
    case "orphaned":
      return "critical";
    case "cancelled":
      return "warn";
    case "completed":
      return "info";
    case "running":
    case "starting":
    case "queued":
    case "stopping":
    default:
      return "info";
  }
}

function jobStateLabel(state: string): string {
  switch (state) {
    case "queued":
      return "В очереди";
    case "starting":
      return "Запускается";
    case "running":
      return "Работает";
    case "stopping":
      return "Останавливается";
    case "completed":
      return "Завершено";
    case "failed":
      return "Сбой";
    case "cancelled":
      return "Отменено";
    case "orphaned":
      return "Потеряно";
    default:
      return state;
  }
}

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  return new Date(parsed).toISOString().slice(11, 19) + "Z";
}

const STATE_COLOR: Record<EntryState, string> = {
  info: "text-[rgb(var(--token-text-primary))]",
  warn: "text-[rgb(var(--token-amber))]",
  err: "text-[rgb(var(--token-red))]",
  critical: "text-[rgb(var(--token-red))]",
};

export function ActivityCard({
  jobs,
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

  const entries = (jobs ?? [])
    .slice()
    .sort((a, b) => {
      const av = a.updated_at ? Date.parse(a.updated_at) : 0;
      const bv = b.updated_at ? Date.parse(b.updated_at) : 0;
      return bv - av;
    })
    .slice(0, 5);

  if (entries.length === 0) {
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
        {entries.map((job) => {
          const entryState = classifyJobState(job.state);
          return (
            <motion.li
              key={job.job_id}
              data-ui-role="activity-entry"
              data-ui-state={entryState}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: [0.0, 0.0, 0.2, 1] }}
              className="flex items-baseline justify-between gap-3 text-xs"
            >
              <span
                className={cn(
                  "truncate font-medium",
                  STATE_COLOR[entryState],
                )}
              >
                {job.job_type}
              </span>
              <span className="text-[rgb(var(--token-text-secondary))]">
                {jobStateLabel(job.state)}
              </span>
              <span className="text-[rgb(var(--token-text-muted))] tabular-nums">
                {formatTime(job.updated_at)}
              </span>
            </motion.li>
          );
        })}
      </ul>
    </article>
  );
}
