interface JobToolbarProps {
  sampleImportDisabled: boolean;
  stopDisabled: boolean;
  onStartSampleImport: () => void;
  onStop: () => void;
}

export function JobToolbar({ sampleImportDisabled, stopDisabled, onStartSampleImport, onStop }: JobToolbarProps) {
  return (
    <section className="panel" aria-labelledby="job-toolbar-title">
      <h2 id="job-toolbar-title">Data Jobs</h2>
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
