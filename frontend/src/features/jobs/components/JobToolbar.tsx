interface JobToolbarProps {
  startDisabled: boolean;
  stopDisabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function JobToolbar({ startDisabled, stopDisabled, onStart, onStop }: JobToolbarProps) {
  return (
    <section className="panel" aria-labelledby="job-toolbar-title">
      <h2 id="job-toolbar-title">Data Jobs</h2>
      <p className="toolbar-hint">One deterministic background flow to validate start, stop, progress, logs, and cleanup.</p>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={startDisabled}>
          Start Sample Import
        </button>
        <button type="button" className="button-secondary" onClick={onStop} disabled={stopDisabled}>
          Stop Selected Job
        </button>
      </div>
    </section>
  );
}
