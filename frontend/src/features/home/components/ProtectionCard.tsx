import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { RiskBlock } from "../../../shared/contracts";
import { ProtectionChip } from "./ProtectionChip";
import { SkeletonBox } from "./SkeletonBox";

export interface ProtectionCardProps {
  risk: RiskBlock;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function ProtectionCard({
  risk,
  isLoading,
  isError,
  onRetry,
}: ProtectionCardProps) {
  const by = risk.by_state;

  const state =
    by.unprotected > 0 || by.failed > 0
      ? "critical"
      : by.repairing > 0 || by.pending > 0
        ? "warning"
        : "ok";

  if (isError) {
    return (
      <article
        data-ui-role="protection-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Защита позиций
        </h3>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось загрузить состояние защиты.
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
        data-ui-role="protection-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="protection-card" width="50%" height="0.9rem" />
        <SkeletonBox scope="protection-card" width="80%" height="1.5rem" />
        <SkeletonBox scope="protection-card" width="60%" height="0.8rem" />
      </article>
    );
  }

  if (risk.positions_total === 0) {
    return (
      <article
        data-ui-role="protection-card"
        data-ui-scope="home"
        data-ui-state="ok"
        className={cn(
          "panel rounded-xl border p-4 flex flex-col gap-2",
          "border-white/10",
        )}
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Защита позиций
        </h3>
        <p className="text-sm text-[rgb(var(--token-text-secondary))]">
          Нет открытых позиций.
        </p>
      </article>
    );
  }

  return (
    <article
      data-ui-role="protection-card"
      data-ui-scope="home"
      data-ui-state={state}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-3",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Защита позиций
        </h3>
        <span className="text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))] tabular-nums">
          {by.protected}/{risk.positions_total} защищены
        </span>
      </header>

      <div className="flex flex-wrap gap-2">
        {by.protected > 0 ? (
          <ProtectionChip
            state="protected"
            count={by.protected}
            label="OK"
          />
        ) : null}
        {by.repairing > 0 ? (
          <ProtectionChip
            state="attention"
            count={by.repairing}
            label="ATT"
          />
        ) : null}
        {by.pending > 0 ? (
          <ProtectionChip
            state="pending"
            count={by.pending}
            label="WAIT"
          />
        ) : null}
        {by.unprotected > 0 ? (
          <ProtectionChip
            state="unprotected"
            count={by.unprotected}
            label="OPEN"
          />
        ) : null}
        {by.failed > 0 ? (
          <ProtectionChip
            state="failed"
            count={by.failed}
            label="FAIL"
          />
        ) : null}
      </div>
    </article>
  );
}
