import { LogEntry } from "../../../shared/contracts";

interface LogViewerProps {
  entries: LogEntry[];
  emptyMessage: string;
}

export function LogViewer({ entries, emptyMessage }: LogViewerProps) {
  return (
    <section className="panel log-viewer" aria-labelledby="logs-viewer-title">
      <h2 id="logs-viewer-title">Log Stream</h2>
      {entries.length === 0 ? (
        <p className="panel-muted" data-testid="logs.viewer.empty">
          {emptyMessage}
        </p>
      ) : (
        <ol className="log-panel__list" data-testid="logs.viewer.list">
          {entries.map((entry) => (
            <li key={entry.entry_id} className="log-panel__item" data-level={entry.level}>
              <div className="log-panel__meta">
                <span>{entry.level}</span>
                <span>{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : "n/a"}</span>
              </div>
              <p className="log-panel__message">{entry.message}</p>
              <p className="panel-muted" data-testid={`logs.entry.${entry.channel}`}>
                {entry.source}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
