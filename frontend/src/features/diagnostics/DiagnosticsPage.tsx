import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { useDiagnosticsModel } from "./hooks/useDiagnosticsModel";

function boolLabel(value: boolean) {
  return value ? "yes" : "no";
}

export function DiagnosticsPage() {
  const diagnosticsQuery = useDiagnosticsModel();
  const snapshot = diagnosticsQuery.data;
  const configEntries = snapshot?.config ?? [];
  const pathEntries = snapshot?.paths ?? [];
  const warnings = snapshot?.warnings ?? [];

  return (
    <AppShell>
      <div className="app-route diagnostics-layout">
        <PageIntro
          eyebrow="Диагностика"
          title="Диагностика совместимости"
          description="Конфигурация, пути и предупреждения совместимости — только чтение."
          meta={
            <>
              <p className="status-caption" data-testid="diagnostics.source-mode">
                Режим: {snapshot?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">Предупреждений: {snapshot?.summary.warnings_count ?? "загрузка"}</p>
              <p className="status-caption">Отсутствующих путей: {snapshot?.summary.missing_paths_count ?? "загрузка"}</p>
              <p className="status-caption">Режим рантайма: {snapshot?.summary.runtime_control_mode ?? "загрузка"}</p>
            </>
          }
        />

        {diagnosticsQuery.isError ? (
          <section className="panel diagnostics-warning-panel">
            <SectionHeading
              title="Ошибка диагностики"
              description="Маршрут остаётся доступным только для чтения."
            />
            <p className="inline-error" data-testid="diagnostics.error">
              Не удалось загрузить снепшот диагностики.
            </p>
          </section>
        ) : null}

        <section className="panel diagnostics-summary-panel">
          <SectionHeading
            title="Снепшот совместимости"
            description="Текущее окружение, фикстуры и состояние путей."
          />
          <div className="diagnostics-summary-grid">
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.routes">
              <p className="diagnostics-summary-card__eyebrow">Покрытие</p>
              <p className="diagnostics-summary-card__label">Маршруты</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.routes_count ?? "..."}</p>
              <p className="summary-card__note">Количество зарегистрированных маршрутов.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.fixtures">
              <p className="diagnostics-summary-card__eyebrow">Входные данные</p>
              <p className="diagnostics-summary-card__label">Фикстурные переопределения</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.fixture_overrides_count ?? "..."}</p>
              <p className="summary-card__note">Текущие фикстурные входные данные в настройках.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.missing-paths">
              <p className="diagnostics-summary-card__eyebrow">Пути</p>
              <p className="diagnostics-summary-card__label">Отсутствующих путей</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.missing_paths_count ?? "..."}</p>
              <p className="summary-card__note">Недостающие пути в снепшоте диагностики.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.runtime-mode">
              <p className="diagnostics-summary-card__eyebrow">Управление</p>
              <p className="diagnostics-summary-card__label">Режим рантайма</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.runtime_control_mode ?? "..."}</p>
              <p className="summary-card__note">Текущий режим управления рантаймом.</p>
            </section>
          </div>
        </section>

        <section className="panel diagnostics-panel">
          <SectionHeading title="Конфигурация" description="Скрыто там где необходимо. Редактирование настроек недоступно." />
          {configEntries.length > 0 ? (
            <div className="surface-table-wrap">
              <table className="surface-table">
                <thead>
                  <tr>
                    <th>Параметр</th>
                    <th>Значение</th>
                    <th>Скрыто</th>
                  </tr>
                </thead>
                <tbody>
                  {configEntries.map((entry, index) => (
                    <tr key={entry.key} data-testid={`diagnostics.config.${index}`}>
                      <td className="surface-table__primary">{entry.label}</td>
                      <td>
                        <span className="diagnostics-code">{entry.value}</span>
                      </td>
                      <td>
                        <span className={entry.masked ? "surface-badge surface-badge--soft" : "surface-badge"}>
                          {boolLabel(entry.masked)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.config.empty">
              <strong>Записей конфигурации нет</strong>
              <p>Текущий снепшот не содержит значений конфигурации.</p>
            </div>
          )}
        </section>

        <section className="panel diagnostics-panel">
          <SectionHeading title="Пути" description="Диагностика путей — только чтение." />
          {pathEntries.length > 0 ? (
            <div className="surface-table-wrap">
              <table className="surface-table">
                <thead>
                  <tr>
                    <th>Параметр</th>
                    <th>Источник</th>
                    <th>Тип</th>
                    <th>Существует</th>
                    <th>Путь</th>
                  </tr>
                </thead>
                <tbody>
                  {pathEntries.map((entry) => (
                    <tr key={entry.key} data-testid={`diagnostics.path.${entry.key}`}>
                      <td className="surface-table__primary">{entry.label}</td>
                      <td>
                        <span className="surface-badge surface-badge--soft">{entry.source}</span>
                      </td>
                      <td>{entry.kind}</td>
                      <td>
                        <span className={entry.exists ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                          {boolLabel(entry.exists)}
                        </span>
                      </td>
                      <td>
                        <span className="diagnostics-code diagnostics-code--path">{entry.path}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.paths.empty">
              <strong>Путей нет</strong>
              <p>Текущий снепшот диагностики не содержит записей путей.</p>
            </div>
          )}
        </section>

        <section className="panel diagnostics-warning-panel">
          <SectionHeading title="Предупреждения" description="Предупреждения совместимости — только чтение." />
          {warnings.length > 0 ? (
            <ul className="diagnostics-warning-list">
              {warnings.map((warning, index) => (
                <li key={`${warning}-${index}`} data-testid={`diagnostics.warning.${index}`} className="diagnostics-warning-item">
                  <span className="diagnostics-warning-item__badge">Внимание</span>
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.warnings.empty">
              <strong>Предупреждений нет</strong>
              <p>В текущем снепшоте диагностики предупреждений не обнаружено.</p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
