import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface DataIntegrityJobCardProps {
  disabled: boolean;
  onStart: () => void;
}

export function DataIntegrityJobCard({ disabled, onStart }: DataIntegrityJobCardProps) {
  return (
    <section className="panel job-action-card job-preset-card">
      <SectionHeading
        title="Data Integrity Job"
        description="Read-only validation for the fixed-preset data backfill DB on the existing Job Manager path."
      />
      <p className="toolbar-hint">Bounded validation only, with no repair/write actions and no broad data maintenance console.</p>
      <dl className="job-preset-grid">
        <dt>Symbol</dt>
        <dd data-testid="jobs.integrity.symbol">BTCUSDT</dd>
        <dt>Category</dt>
        <dd data-testid="jobs.integrity.category">spot</dd>
        <dt>Interval</dt>
        <dd data-testid="jobs.integrity.interval">1m</dd>
      </dl>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={disabled}>
          Start Data Integrity
        </button>
      </div>
    </section>
  );
}
