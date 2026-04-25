import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface JobToolbarProps {
  sampleImportDisabled: boolean;
  stopDisabled: boolean;
  onStartSampleImport: () => void;
  onStop: () => void;
}

export function JobToolbar({ sampleImportDisabled, stopDisabled, onStartSampleImport, onStop }: JobToolbarProps) {
  return (
    <section className="panel job-action-card" data-ui-role="job-toolbar" data-ui-scope="default">
      <SectionHeading
        title="Задачи данных"
        description="Быстрый запуск импорта и управление активной задачей."
      />
      <p className="toolbar-hint">Детерминированный импорт и загрузка реальных данных через Job Manager.</p>
      <div className="toolbar-actions" data-ui-role="action-row" data-ui-scope="jobs-toolbar">
        <button
          type="button"
          className="button-primary"
          onClick={onStartSampleImport}
          disabled={sampleImportDisabled}
          data-ui-role="job-action"
          data-ui-scope="sample-import"
          data-ui-action="start"
          data-ui-state={sampleImportDisabled ? "disabled" : "enabled"}
        >
          Запустить импорт
        </button>
        <button
          type="button"
          className="button-secondary"
          onClick={onStop}
          disabled={stopDisabled}
          data-ui-role="job-action"
          data-ui-scope="selected"
          data-ui-action="stop"
          data-ui-state={stopDisabled ? "disabled" : "enabled"}
        >
          Остановить задачу
        </button>
      </div>
    </section>
  );
}
