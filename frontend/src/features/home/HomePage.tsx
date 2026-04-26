import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { AppShell } from "../../shared/ui/AppShell";
import { fadeIn, staggerContainer, staggerItem } from "../../styles/motion";
import { ActivityCard } from "./components/ActivityCard";
import { ConnectionsCard } from "./components/ConnectionsCard";
import { HeroStatusCard } from "./components/HeroStatusCard";
import { HomeFooter } from "./components/HomeFooter";
import { MLPipelineCard } from "./components/MLPipelineCard";
import { ProtectionCard } from "./components/ProtectionCard";
import { ReconciliationCard } from "./components/ReconciliationCard";
import { TradingCard } from "./components/TradingCard";
import { useHomeData } from "./hooks/useHomeData";
import { useHomeDerivedState } from "./hooks/useHomeDerivedState";

export function HomePage() {
  const navigate = useNavigate();
  const home = useHomeData();
  const derived = useHomeDerivedState(home.data, home.errors);

  const handlePrimaryAction = (kind: string) => {
    if (derived.global.primary_action?.href) {
      navigate(derived.global.primary_action.href);
    } else if (kind === "open-futures") navigate("/futures");
    else if (kind === "open-runtime") navigate("/runtime");
    else if (kind === "open-diagnostics") navigate("/diagnostics");
  };

  const heroIsLoading = home.isLoading && !derived.hasAnyData;
  const heroIsError = home.isAllError;

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
          summary={derived.global}
          isLoading={heroIsLoading}
          isError={heroIsError}
          onRetry={home.refetch.all}
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
              derived={derived}
              isLoading={
                (home.data.spot === undefined || home.data.futures === undefined) &&
                home.errors.spot === null &&
                home.errors.futures === null
              }
              isError={home.errors.spot !== null && home.errors.futures !== null}
              onRetry={() => {
                home.refetch.spot();
                home.refetch.futures();
                home.refetch.runtime();
              }}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ProtectionCard
              derived={derived}
              isLoading={home.data.futures === undefined && home.errors.futures === null}
              isError={home.errors.futures !== null}
              onRetry={home.refetch.futures}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ReconciliationCard
              derived={derived}
              generatedAt={home.generatedAt}
              isLoading={
                home.data.diagnostics === undefined && home.errors.diagnostics === null
              }
              isError={home.errors.diagnostics !== null}
              onRetry={home.refetch.diagnostics}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <MLPipelineCard
              derived={derived}
              isLoading={home.data.models === undefined && home.errors.models === null}
              isError={home.errors.models !== null}
              onRetry={home.refetch.models}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ConnectionsCard
              derived={derived}
              isLoading={
                home.data.runtime === undefined &&
                home.data.telegram === undefined &&
                home.errors.runtime === null &&
                home.errors.telegram === null
              }
              isError={
                home.errors.runtime !== null &&
                home.errors.telegram !== null &&
                home.errors.diagnostics !== null
              }
              onRetry={() => {
                home.refetch.runtime();
                home.refetch.telegram();
                home.refetch.diagnostics();
              }}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ActivityCard
              jobs={home.data.jobs}
              isLoading={home.data.jobs === undefined && home.errors.jobs === null}
              isError={home.errors.jobs !== null}
              onRetry={home.refetch.jobs}
            />
          </motion.div>
        </motion.div>

        <HomeFooter
          generatedAt={home.generatedAt}
          version={home.data.health?.version ?? null}
          service={home.data.health?.service ?? null}
        />
      </motion.div>
    </AppShell>
  );
}
