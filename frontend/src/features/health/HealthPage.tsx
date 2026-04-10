import { useQuery } from "@tanstack/react-query";
import { getBootstrap, getHealth } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";

export function HealthPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
  });

  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: getBootstrap,
  });

  return (
    <AppShell>
      <section className="panel" aria-labelledby="foundation-health-title">
        <h2 id="foundation-health-title">Foundation Health</h2>
        <p data-testid="health.status">
          Health: {health.isLoading ? "loading" : health.data?.status ?? "unavailable"}
        </p>
        <p data-testid="health.service">
          Service: {health.data?.service ?? "n/a"}
        </p>
        <p data-testid="health.version">
          Version: {health.data?.version ?? "n/a"}
        </p>
      </section>

      <section className="panel" aria-labelledby="foundation-bootstrap-title">
        <h2 id="foundation-bootstrap-title">Bootstrap</h2>
        <p data-testid="bootstrap.app-name">
          App: {bootstrap.isLoading ? "loading" : bootstrap.data?.app_name ?? "n/a"}
        </p>
        <p data-testid="bootstrap.session-id">
          Session: {bootstrap.data?.session.session_id ?? "n/a"}
        </p>
        <p data-testid="bootstrap.routes">
          Routes: {bootstrap.data?.routes.join(", ") ?? "n/a"}
        </p>
      </section>
    </AppShell>
  );
}
