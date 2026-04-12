import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface JobToolbarProps {
  sampleImportDisabled: boolean;
  stopDisabled: boolean;
  onStartSampleImport: () => void;
  onStop: () => void;
}

export function JobToolbar({ sampleImportDisabled, stopDisabled, onStartSampleImport, onStop }: JobToolbarProps) {
  return (
    <section className="panel job-action-card">
      <SectionHeading
        title="Data Jobs"
        description="Quick-start actions for the deterministic import flow and the currently selected running job."
      />
      <p className="toolbar-hint">Existing deterministic import flow plus one fixed-preset real backfill job on the same Job Manager path.</p>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStartSampleImport} disabled={sampleImportDisabled}>
          Start Sample Import
        </button>
        <button type="button" className="button-secondary" onClick={onStop} disabled={stopDisabled}>
          Stop Selected Job
        </button>
      </div>
    </section>
  );
}
