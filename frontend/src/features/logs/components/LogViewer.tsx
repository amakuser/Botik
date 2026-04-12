import { SectionHeading } from "../../../shared/ui/SectionHeading";
import { LogEntry } from "../../../shared/contracts";

interface LogViewerProps {
  entries: LogEntry[];
  emptyMessage: string;
}

export function LogViewer({ entries, emptyMessage }: LogViewerProps) {
  return (
    <section className="panel log-viewer">
      <SectionHeading title="Log Stream" description="Recent bounded entries for the selected channel, with live append when the stream is connected." />
      {entries.length === 0 ? (
        <p className="panel-muted log-viewer__empty" data-testid="logs.viewer.empty">
          {emptyMessage}
        </p>
      ) : (
        <ol className="log-panel__list" data-testid="logs.viewer.list">
          {entries.map((entry) => (
            <li key={entry.entry_id} className="log-panel__item" data-level={entry.level}>
              <div className="log-panel__meta">
                <span className="log-panel__level">{entry.level}</span>
                <span>{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : "n/a"}</span>
              </div>
              <p className="log-panel__message">{entry.message}</p>
              <p className="panel-muted log-viewer__source" data-testid={`logs.entry.${entry.channel}`}>
                {entry.source}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
