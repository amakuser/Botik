import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type {
  ReconciliationBlock,
  ReconciliationState,
} from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface ReconciliationCardProps {
  reconciliation: ReconciliationBlock;
  generatedAt: string | null;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const LABEL: Record<ReconciliationState, string> = {
  healthy: "Свежая",
  degraded: "Расхождения",
  stale: "Устаревшая",
  failed: "Сбой",
  unsupported: "Недоступно",
};

const DOT_STATE: Record<ReconciliationState, "ok" | "warning" | "critical" | "unknown"> = {
  healthy: "ok",
  degraded: "warning",
  stale: "warning",
  failed: "critical",
  unsupported: "unknown",
};

function formatGeneratedAt(iso: string | null): string {
  if (!iso) return "Недоступно";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "Недоступно";
  const date = new Date(parsed);
  return date.toISOString().slice(11, 19) + "Z";
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return "Недоступно";
  return `${Math.round(seconds)}s`;
}

export function ReconciliationCard({
  reconciliation,
  generatedAt,
  isLoading,
  isError,
  onRetry,
}: ReconciliationCardProps) {
  if (isError) {
    return (
      <article
        data-ui-role="reconciliation-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Reconciliation
        </h3>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось получить состояние reconciliation.
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
        data-ui-role="reconciliation-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="reconciliation-card" width="50%" height="0.9rem" />
        <SkeletonBox scope="reconciliation-card" width="70%" height="1.5rem" />
        <SkeletonBox scope="reconciliation-card" width="60%" height="0.8rem" />
      </article>
    );
  }

  if (reconciliation.state === "unsupported") {
    return (
      <article
        data-ui-role="reconciliation-card"
        data-ui-scope="home"
        data-ui-state="unsupported"
        className={cn(
          "panel rounded-xl border p-4 flex flex-col gap-2",
          "border-white/10",
        )}
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Reconciliation
        </h3>
        <p className="text-sm text-[rgb(var(--token-text-secondary))]">
          Reconciliation недоступна в текущем executor.
        </p>
      </article>
    );
  }

  return (
    <article
      data-ui-role="reconciliation-card"
      data-ui-scope="home"
      data-ui-state={reconciliation.state}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-2",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Reconciliation
        </h3>
        <StatusDot state={DOT_STATE[reconciliation.state]} size="sm" />
      </header>
      <p
        className="text-base font-medium text-[rgb(var(--token-text-primary))]"
        data-testid="home.reconciliation.label"
      >
        {LABEL[reconciliation.state]}
      </p>
      <dl className="grid grid-cols-2 gap-y-1 text-xs text-[rgb(var(--token-text-secondary))]">
        <dt>Расхождения</dt>
        <dd className="text-right tabular-nums text-[rgb(var(--token-text-primary))]">
          {reconciliation.drift_count}
        </dd>
        <dt>Возраст снимка</dt>
        <dd className="text-right tabular-nums text-[rgb(var(--token-text-primary))]">
          {formatAge(reconciliation.last_run_age_seconds)}
        </dd>
      </dl>
      <p className="text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))] tabular-nums">
        Снепшот: {formatGeneratedAt(generatedAt)}
      </p>
    </article>
  );
}
