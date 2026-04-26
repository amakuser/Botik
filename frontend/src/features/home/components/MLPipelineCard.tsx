import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { HomeDerivedState } from "../hooks/useHomeDerivedState";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface MLPipelineCardProps {
  derived: HomeDerivedState;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const STATE_DOT: Record<string, "ok" | "warning" | "critical" | "unknown"> = {
  ok: "ok",
  warning: "warning",
  error: "critical",
  idle: "unknown",
};

const STATE_LABEL: Record<string, string> = {
  ok: "Готово",
  warning: "Внимание",
  error: "Ошибка",
  idle: "Не активно",
};

export function MLPipelineCard({
  derived,
  isLoading,
  isError,
  onRetry,
}: MLPipelineCardProps) {
  const ml = derived.mlPipeline;

  if (isError) {
    return (
      <article
        data-ui-role="ml-pipeline-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          ML Pipeline
        </h3>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось загрузить состояние моделей.
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
        data-ui-role="ml-pipeline-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="ml-pipeline-card" width="50%" height="0.9rem" />
        <SkeletonBox scope="ml-pipeline-card" width="70%" height="1.5rem" />
        <SkeletonBox scope="ml-pipeline-card" width="60%" height="0.8rem" />
      </article>
    );
  }

  return (
    <article
      data-ui-role="ml-pipeline-card"
      data-ui-scope="home"
      data-ui-state={ml.state}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-2",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          ML Pipeline
        </h3>
        <StatusDot state={STATE_DOT[ml.state] ?? "unknown"} size="sm" />
      </header>
      <p
        className="text-base font-medium text-[rgb(var(--token-text-primary))]"
        data-testid="home.ml.label"
      >
        {STATE_LABEL[ml.state] ?? "—"}
      </p>
      <dl className="grid grid-cols-2 gap-y-1 text-xs text-[rgb(var(--token-text-secondary))]">
        <dt>Готовых scope</dt>
        <dd className="text-right tabular-nums text-[rgb(var(--token-text-primary))]">
          {ml.readyScopes}/{ml.totalScopes}
        </dd>
        <dt>Последний run</dt>
        <dd className="text-right text-[rgb(var(--token-text-primary))]">
          {ml.latestRunStatus}
        </dd>
      </dl>
      {ml.detail ? (
        <p className="text-[0.7rem] text-[rgb(var(--token-text-muted))]">{ml.detail}</p>
      ) : null}
    </article>
  );
}
