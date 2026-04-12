import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { startRuntime, stopRuntime } from "../../shared/api/client";
import { RuntimeStatus } from "../../shared/contracts";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { RuntimeStatusCard } from "./components/RuntimeStatusCard";
import { useRuntimeStatus } from "./hooks/useRuntimeStatus";

export function RuntimeStatusPage() {
  const queryClient = useQueryClient();
  const runtimeStatusQuery = useRuntimeStatus();
  const runtimes = runtimeStatusQuery.data?.runtimes ?? [];
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<`${RuntimeStatus["runtime_id"]}:${"start" | "stop"}` | null>(null);

  async function runAction(runtimeId: RuntimeStatus["runtime_id"], action: "start" | "stop") {
    setActionError(null);
    setPendingAction(`${runtimeId}:${action}`);
    try {
      if (action === "start") {
        await startRuntime(runtimeId);
      } else {
        await stopRuntime(runtimeId);
      }
      await queryClient.invalidateQueries({ queryKey: ["runtime-status"] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `Failed to ${action} ${runtimeId}.`);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <AppShell>
      <div className="app-route runtime-layout">
        <PageIntro
          eyebrow="Operations"
          title="Runtime Control"
          description="Bounded start and stop controls for the active trading runtimes, with the same observable heartbeat and last-error status model."
        />

        {runtimeStatusQuery.isError ? (
          <section className="panel">
            <h2>Runtime Control Error</h2>
            <p className="inline-error" data-testid="runtime.error.banner">
              Failed to load runtime status.
            </p>
          </section>
        ) : null}

        {actionError ? (
          <section className="panel">
            <h2>Action Error</h2>
            <p className="inline-error" data-testid="runtime.action-error">
              {actionError}
            </p>
          </section>
        ) : null}

        <section className="runtime-grid">
          {runtimes.map((runtime) => (
            <RuntimeStatusCard
              key={runtime.runtime_id}
              runtime={runtime}
              startDisabled={Boolean(pendingAction) || !["offline", "unknown"].includes(runtime.state)}
              stopDisabled={Boolean(pendingAction) || ["offline", "unknown"].includes(runtime.state)}
              onStart={() => void runAction(runtime.runtime_id, "start")}
              onStop={() => void runAction(runtime.runtime_id, "stop")}
            />
          ))}
        </section>
      </div>
    </AppShell>
  );
}
