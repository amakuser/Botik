import { cn } from "../../../shared/lib/utils";

export interface HomeFooterProps {
  generatedAt: string | null;
  version: string | null;
  service: string | null;
  className?: string;
}

function formatGeneratedAt(iso: string | null): string {
  if (!iso) return "—";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  return new Date(parsed).toISOString().slice(0, 19).replace("T", " ") + "Z";
}

export function HomeFooter({
  generatedAt,
  version,
  service,
  className,
}: HomeFooterProps) {
  return (
    <footer
      data-ui-role="home-footer"
      data-ui-scope="home"
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 px-1 pt-2 pb-1",
        "text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))]",
        className,
      )}
    >
      <span data-testid="home.footer.sync" className="tabular-nums">
        Синхронизация: {formatGeneratedAt(generatedAt)}
      </span>
      <span data-testid="home.footer.version">
        {service ?? "app-service"} · v{version ?? "—"}
      </span>
    </footer>
  );
}
