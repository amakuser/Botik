import { AppShell } from "../../shared/ui/AppShell";
import { RuntimeStatusCard } from "./components/RuntimeStatusCard";
import { useRuntimeStatus } from "./hooks/useRuntimeStatus";

export function RuntimeStatusPage() {
  const runtimeStatusQuery = useRuntimeStatus();
  const runtimes = runtimeStatusQuery.data?.runtimes ?? [];

  return (
    <AppShell>
      <div className="runtime-layout">
        <section className="panel">
          <h2>Runtime Status</h2>
          <p className="panel-muted">
            Read-only presence, heartbeat, and last-error status for the current trading runtimes.
          </p>
        </section>

        {runtimeStatusQuery.isError ? (
          <section className="panel">
            <h2>Runtime Status Error</h2>
            <p className="inline-error" data-testid="runtime.error.banner">
              Failed to load runtime status.
            </p>
          </section>
        ) : null}

        <section className="runtime-grid">
          {runtimes.map((runtime) => (
            <RuntimeStatusCard key={runtime.runtime_id} runtime={runtime} />
          ))}
        </section>
      </div>
    </AppShell>
  );
}
