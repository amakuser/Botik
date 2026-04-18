import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface DataBackfillJobCardProps {
  disabled: boolean;
  onStart: () => void;
}

export function DataBackfillJobCard({ disabled, onStart }: DataBackfillJobCardProps) {
  return (
    <section className="panel job-action-card job-preset-card">
      <SectionHeading
        title="Загрузка данных"
        description="Запуск задачи загрузки исторических данных."
      />
      <p className="toolbar-hint">
        Один фиксированный пресет — быстрый запуск без дополнительных настроек.
      </p>
      <dl className="job-preset-grid">
        <dt>Символ</dt>
        <dd data-testid="jobs.backfill.symbol">BTCUSDT</dd>
        <dt>Категория</dt>
        <dd data-testid="jobs.backfill.category">spot</dd>
        <dt>Интервал</dt>
        <dd data-testid="jobs.backfill.interval">1m</dd>
      </dl>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={disabled}>
          Запустить загрузку
        </button>
      </div>
    </section>
  );
}
