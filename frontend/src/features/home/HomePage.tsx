import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { AppShell } from "../../shared/ui/AppShell";
import { fadeIn, staggerContainer, staggerItem } from "../../styles/motion";
import type {
  GlobalBlock,
  TradingBlock,
  RiskBlock,
  ReconciliationBlock,
  MLBlock,
  ConnectionsBlock,
} from "../../shared/contracts";
import { ActivityCard } from "./components/ActivityCard";
import { ConnectionsCard } from "./components/ConnectionsCard";
import { HeroStatusCard } from "./components/HeroStatusCard";
import { HomeFooter } from "./components/HomeFooter";
import { MLPipelineCard } from "./components/MLPipelineCard";
import { ProtectionCard } from "./components/ProtectionCard";
import { ReconciliationCard } from "./components/ReconciliationCard";
import { TradingCard } from "./components/TradingCard";
import { useHomeSummary } from "./hooks/useHomeSummary";

const FALLBACK_GLOBAL: GlobalBlock = {
  state: "healthy",
  health_score: 0,
  critical_reason: null,
  primary_action: null,
};

const FALLBACK_TRADING: TradingBlock = {
  spot: { state: "unknown", lag_seconds: null },
  futures: { state: "unknown", lag_seconds: null },
  today_pnl: null,
  today_pnl_series: null,
};

const FALLBACK_RISK: RiskBlock = {
  positions_total: 0,
  by_state: {
    protected: 0,
    pending: 0,
    unprotected: 0,
    repairing: 0,
    failed: 0,
  },
  positions: [],
};

const FALLBACK_RECONCILIATION: ReconciliationBlock = {
  state: "unsupported",
  last_run_at: null,
  last_run_age_seconds: null,
  next_run_in_seconds: null,
  drift_count: 0,
};

const FALLBACK_ML: MLBlock = {
  pipeline_state: "unknown",
  active_model: null,
  last_training_run: null,
};

const FALLBACK_CONNECTIONS: ConnectionsBlock = {
  bybit: null,
  telegram: null,
  database: "unavailable",
};

export function HomePage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useHomeSummary();

  const handleRetry = (): void => {
    void refetch();
  };

  const handlePrimaryAction = (kind: string): void => {
    if (kind === "open-diagnostics") navigate("/diagnostics");
    else if (kind === "pause-trading") navigate("/runtime");
  };

  const summary = data;

  // Hero is in loading state only on the very first render before data arrives.
  // Once data is present, polling refetches keep `isLoading` false (React Query).
  const heroIsLoading = isLoading && summary === undefined;
  const heroIsError = isError && summary === undefined;

  // When summary is undefined, all per-card skeletons should also be visible.
  const cardIsLoading = summary === undefined && !isError;
  const cardIsError = summary === undefined && isError;

  const global = summary?.global ?? FALLBACK_GLOBAL;
  const trading = summary?.trading ?? FALLBACK_TRADING;
  const risk = summary?.risk ?? FALLBACK_RISK;
  const reconciliation = summary?.reconciliation ?? FALLBACK_RECONCILIATION;
  const ml = summary?.ml ?? FALLBACK_ML;
  const connections = summary?.connections ?? FALLBACK_CONNECTIONS;
  const activity = summary?.activity ?? [];
  const generatedAt = summary?.generated_at ?? null;

  return (
    <AppShell>
      <motion.div
        className="app-route flex flex-col gap-4"
        {...fadeIn}
        data-ui-role="page"
        data-ui-scope="home"
        data-testid="home.page"
      >
        <HeroStatusCard
          summary={global}
          isLoading={heroIsLoading}
          isError={heroIsError}
          onRetry={handleRetry}
          onPrimaryAction={handlePrimaryAction}
        />

        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          variants={staggerContainer}
          initial="initial"
          animate="animate"
        >
          <motion.div variants={staggerItem}>
            <TradingCard
              trading={trading}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ProtectionCard
              risk={risk}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ReconciliationCard
              reconciliation={reconciliation}
              generatedAt={generatedAt}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <MLPipelineCard
              ml={ml}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ConnectionsCard
              connections={connections}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ActivityCard
              activity={activity}
              isLoading={cardIsLoading}
              isError={cardIsError}
              onRetry={handleRetry}
            />
          </motion.div>
        </motion.div>

        <HomeFooter generatedAt={generatedAt} />
      </motion.div>
    </AppShell>
  );
}
