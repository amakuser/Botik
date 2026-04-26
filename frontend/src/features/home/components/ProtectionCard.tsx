import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { HomeDerivedState } from "../hooks/useHomeDerivedState";
import { ProtectionChip } from "./ProtectionChip";
import { SkeletonBox } from "./SkeletonBox";

export interface ProtectionCardProps {
  derived: HomeDerivedState;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function ProtectionCard({
  derived,
  isLoading,
  isError,
  onRetry,
}: ProtectionCardProps) {
  const { protection } = derived;

  const state =
    protection.unprotected > 0 || protection.failed > 0
      ? "critical"
      : protection.attention > 0 || protection.pending > 0
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

  if (protection.total === 0) {
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
          {protection.protected}/{protection.total} защищены
        </span>
      </header>

      <div className="flex flex-wrap gap-2">
        {protection.protected > 0 ? (
          <ProtectionChip
            state="protected"
            count={protection.protected}
            label="OK"
          />
        ) : null}
        {protection.attention > 0 ? (
          <ProtectionChip
            state="attention"
            count={protection.attention}
            label="ATT"
          />
        ) : null}
        {protection.pending > 0 ? (
          <ProtectionChip
            state="pending"
            count={protection.pending}
            label="WAIT"
          />
        ) : null}
        {protection.unprotected > 0 ? (
          <ProtectionChip
            state="unprotected"
            count={protection.unprotected}
            label="OPEN"
          />
        ) : null}
        {protection.failed > 0 ? (
          <ProtectionChip
            state="failed"
            count={protection.failed}
            label="FAIL"
          />
        ) : null}
      </div>
    </article>
  );
}
