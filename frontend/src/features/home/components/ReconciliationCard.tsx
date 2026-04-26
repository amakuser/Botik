import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { HomeDerivedState } from "../hooks/useHomeDerivedState";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface ReconciliationCardProps {
  derived: HomeDerivedState;
  generatedAt: string | null;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const LABEL: Record<string, string> = {
  ok: "Свежая",
  stale: "Устаревшая",
  failed: "Сбой",
  unavailable: "Недоступно",
};

const DOT_STATE: Record<string, "ok" | "warning" | "critical" | "unknown"> = {
  ok: "ok",
  stale: "warning",
  failed: "critical",
  unavailable: "unknown",
};

function formatGeneratedAt(iso: string | null): string {
  if (!iso) return "—";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  const date = new Date(parsed);
  return date.toISOString().slice(11, 19) + "Z";
}

export function ReconciliationCard({
  derived,
  generatedAt,
  isLoading,
  isError,
  onRetry,
}: ReconciliationCardProps) {
  const { reconciliation } = derived;

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

  if (reconciliation.state === "unavailable") {
    return (
      <article
        data-ui-role="reconciliation-card"
        data-ui-scope="home"
        data-ui-state="unavailable"
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
        <StatusDot state={DOT_STATE[reconciliation.state] ?? "unknown"} size="sm" />
      </header>
      <p
        className="text-base font-medium text-[rgb(var(--token-text-primary))]"
        data-testid="home.reconciliation.label"
      >
        {LABEL[reconciliation.state] ?? "Неизвестно"}
      </p>
      {reconciliation.detail ? (
        <p className="text-xs text-[rgb(var(--token-text-secondary))]">
          {reconciliation.detail}
        </p>
      ) : null}
      <p className="text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))] tabular-nums">
        Снепшот: {formatGeneratedAt(generatedAt)}
      </p>
    </article>
  );
}
