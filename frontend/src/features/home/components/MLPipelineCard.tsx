import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { MLBlock, PipelineState } from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface MLPipelineCardProps {
  ml: MLBlock;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const STATE_DOT: Record<PipelineState, "ok" | "warning" | "critical" | "unknown"> = {
  serving: "ok",
  training: "warning",
  idle: "unknown",
  error: "critical",
  unknown: "unknown",
};

const STATE_LABEL: Record<PipelineState, string> = {
  serving: "Готово",
  training: "Обучение",
  idle: "Не активно",
  error: "Ошибка",
  unknown: "Неизвестно",
};

export function MLPipelineCard({
  ml,
  isLoading,
  isError,
  onRetry,
}: MLPipelineCardProps) {
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

  const state = ml.pipeline_state;
  const activeModel = ml.active_model;
  const lastRun = ml.last_training_run;

  return (
    <article
      data-ui-role="ml-pipeline-card"
      data-ui-scope="home"
      data-ui-state={state}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-2",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          ML Pipeline
        </h3>
        <StatusDot state={STATE_DOT[state]} size="sm" />
      </header>
      <p
        className="text-base font-medium text-[rgb(var(--token-text-primary))]"
        data-testid="home.ml.label"
      >
        {STATE_LABEL[state]}
      </p>
      <dl className="grid grid-cols-2 gap-y-1 text-xs text-[rgb(var(--token-text-secondary))]">
        <dt>Активная модель</dt>
        <dd className="text-right text-[rgb(var(--token-text-primary))]">
          {activeModel ? activeModel.version : "Активная модель не назначена"}
        </dd>
        <dt>Последний run</dt>
        <dd className="text-right text-[rgb(var(--token-text-primary))]">
          {lastRun ? lastRun.status : "Недоступно"}
        </dd>
      </dl>
    </article>
  );
}
