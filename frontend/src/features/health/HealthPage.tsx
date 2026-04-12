import { useQuery } from "@tanstack/react-query";
import { getBootstrap, getHealth } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";

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
      <div className="app-route health-layout">
        <PageIntro
          eyebrow="Overview"
          title="Foundation Health"
          description="Primary stack health and bootstrap visibility for the current desktop shell and app-service baseline."
          meta={
            <>
              <p data-testid="health.status">Health: {health.isLoading ? "loading" : health.data?.status ?? "unavailable"}</p>
              <p data-testid="health.service">Service: {health.data?.service ?? "n/a"}</p>
              <p data-testid="health.version">Version: {health.data?.version ?? "n/a"}</p>
            </>
          }
        />

        <section className="panel" aria-labelledby="foundation-bootstrap-title">
          <SectionHeading
            title="Bootstrap"
            description="Current route contract and session details exposed by the primary app-service bootstrap payload."
          />
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
      </div>
    </AppShell>
  );
}
