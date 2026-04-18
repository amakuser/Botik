import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface DataIntegrityJobCardProps {
  disabled: boolean;
  onStart: () => void;
}

export function DataIntegrityJobCard({ disabled, onStart }: DataIntegrityJobCardProps) {
  return (
    <section className="panel job-action-card job-preset-card">
      <SectionHeading
        title="Проверка данных"
        description="Только чтение — валидация загруженных данных без изменений."
      />
      <p className="toolbar-hint">Только проверка целостности, без исправлений и записи.</p>
      <dl className="job-preset-grid">
        <dt>Символ</dt>
        <dd data-testid="jobs.integrity.symbol">BTCUSDT</dd>
        <dt>Категория</dt>
        <dd data-testid="jobs.integrity.category">spot</dd>
        <dt>Интервал</dt>
        <dd data-testid="jobs.integrity.interval">1m</dd>
      </dl>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={disabled}>
          Запустить проверку
        </button>
      </div>
    </section>
  );
}
