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
        title="Задачи данных"
        description="Быстрый запуск импорта и управление активной задачей."
      />
      <p className="toolbar-hint">Детерминированный импорт и загрузка реальных данных через Job Manager.</p>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStartSampleImport} disabled={sampleImportDisabled}>
          Запустить импорт
        </button>
        <button type="button" className="button-secondary" onClick={onStop} disabled={stopDisabled}>
          Остановить задачу
        </button>
      </div>
    </section>
  );
}
