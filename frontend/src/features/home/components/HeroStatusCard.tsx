import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../../shared/lib/utils";
import { Button } from "../../../shared/ui/primitives/Button";
import type { GlobalBlock, GlobalState } from "../../../shared/contracts";
import { HealthRing } from "./HealthRing";
import { SkeletonBox } from "./SkeletonBox";

export interface HeroStatusCardProps {
  summary: GlobalBlock;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPrimaryAction: (kind: string) => void;
}

const TITLE: Record<GlobalState, string> = {
  healthy: "Система работает штатно",
  warning: "Есть предупреждения",
  critical: "Требуется внимание",
};

const SUBTITLE: Record<GlobalState, string> = {
  healthy: "Подсистемы в норме, защита позиций активна.",
  warning: "Часть подсистем работает с ограничениями.",
  critical: "Обнаружены критические условия.",
};

const BORDER: Record<GlobalState, string> = {
  healthy: "border-[rgb(var(--token-green)/0.32)]",
  warning: "border-[rgb(var(--token-amber)/0.36)]",
  critical: "border-[rgb(var(--token-red)/0.45)]",
};

export function HeroStatusCard({
  summary,
  isLoading,
  isError,
  onRetry,
  onPrimaryAction,
}: HeroStatusCardProps) {
  if (isError) {
    return (
      <section
        className={cn(
          "panel rounded-2xl border px-5 py-4",
          "border-[rgb(var(--token-red)/0.45)]",
          "flex flex-wrap items-center gap-4",
        )}
        data-ui-role="hero-status"
        data-ui-scope="home"
        data-ui-state="critical"
        data-testid="home.hero"
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[rgb(var(--token-red)/0.12)] text-[rgb(var(--token-red))] text-2xl">
          ⚠
        </div>
        <div className="flex-1 min-w-[12rem]">
          <h2 className="text-lg font-semibold text-[rgb(var(--token-text-primary))]">
            Не удалось загрузить состояние системы
          </h2>
          <p className="text-sm text-[rgb(var(--token-text-secondary))]">
            Проверьте соединение с app-service и повторите попытку.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={onRetry}
          data-testid="home.hero.retry"
          data-ui-role="primary-action"
          data-ui-action="retry"
          data-ui-state="enabled"
        >
          Повторить
        </Button>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section
        className={cn(
          "panel rounded-2xl border border-white/10 px-5 py-4",
          "flex items-center gap-4 min-h-[140px]",
        )}
        data-ui-role="hero-status"
        data-ui-scope="home"
        data-ui-state="healthy"
        data-testid="home.hero"
      >
        <SkeletonBox scope="hero" width="64px" height="64px" rounded />
        <div className="flex-1 space-y-2">
          <SkeletonBox scope="hero" width="40%" height="1.25rem" />
          <SkeletonBox scope="hero" width="60%" height="0.9rem" />
        </div>
      </section>
    );
  }

  return (
    <section
      className={cn(
        "panel rounded-2xl border px-5 py-4 transition-colors duration-300",
        BORDER[summary.state],
        "flex flex-wrap items-center gap-4 min-h-[140px]",
      )}
      data-ui-role="hero-status"
      data-ui-scope="home"
      data-ui-state={summary.state}
      data-testid="home.hero"
    >
      <HealthRing
        score={summary.health_score}
        state={summary.state}
        size={72}
        ariaLabel={`Health score ${summary.health_score} из 100`}
      />

      <div className="flex-1 min-w-[12rem]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={summary.state}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.0, 0.0, 0.2, 1] }}
          >
            <h2
              className="text-lg font-semibold text-[rgb(var(--token-text-primary))]"
              data-testid="home.hero.title"
            >
              {TITLE[summary.state]}
            </h2>
            <p
              className="text-sm text-[rgb(var(--token-text-secondary))] mt-1"
              data-testid="home.hero.subtitle"
            >
              {summary.critical_reason ?? SUBTITLE[summary.state]}
            </p>
          </motion.div>
        </AnimatePresence>
      </div>

      {summary.state === "critical" && summary.primary_action ? (
        <Button
          onClick={() => onPrimaryAction(summary.primary_action!.kind)}
          data-testid="home.hero.primary-action"
          data-ui-role="primary-action"
          data-ui-action={summary.primary_action.kind}
          data-ui-state="enabled"
        >
          {summary.primary_action.label}
        </Button>
      ) : null}
    </section>
  );
}
