import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface DataBackfillJobCardProps {
  disabled: boolean;
  onStart: () => void;
}

export function DataBackfillJobCard({ disabled, onStart }: DataBackfillJobCardProps) {
  return (
    <section className="panel job-action-card job-preset-card">
      <SectionHeading
        title="Data Backfill Job"
        description="Fixed-preset real backfill flow through the existing app-service, Job Manager, worker, and SSE path."
      />
      <p className="toolbar-hint">
        Single preset only, kept intentionally narrow so operators can launch it quickly without opening a broader data console.
      </p>
      <dl className="job-preset-grid">
        <dt>Symbol</dt>
        <dd data-testid="jobs.backfill.symbol">BTCUSDT</dd>
        <dt>Category</dt>
        <dd data-testid="jobs.backfill.category">spot</dd>
        <dt>Interval</dt>
        <dd data-testid="jobs.backfill.interval">1m</dd>
      </dl>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={disabled}>
          Start Data Backfill
        </button>
      </div>
    </section>
  );
}
