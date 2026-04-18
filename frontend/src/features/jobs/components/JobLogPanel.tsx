import { JobLogEntry } from "../hooks/useJobEvents";
import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface JobLogPanelProps {
  logs: JobLogEntry[];
}

export function JobLogPanel({ logs }: JobLogPanelProps) {
  return (
    <section className="panel log-panel">
      <SectionHeading title="Логи задачи" description="Вывод воркера для выбранной задачи." />
      {logs.length === 0 ? (
        <p className="panel-muted log-panel__empty" data-testid="jobs.logs.empty">
          Логи появятся после запуска задачи.
        </p>
      ) : (
        <ol className="log-panel__list" data-testid="jobs.logs.list">
          {logs.map((entry) => (
            <li key={entry.eventId} className="log-panel__item" data-level={entry.level}>
              <div className="log-panel__meta">
                <span className="log-panel__level">{entry.level}</span>
                <time dateTime={entry.timestamp}>{new Date(entry.timestamp).toLocaleTimeString()}</time>
              </div>
              <p className="log-panel__message">{entry.message}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
