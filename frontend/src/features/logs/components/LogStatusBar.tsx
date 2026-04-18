import { LogChannel } from "../../../shared/contracts";

interface LogStatusBarProps {
  channel: LogChannel | null;
  connected: boolean;
  entryCount: number;
  truncated: boolean;
}

export function LogStatusBar({ channel, connected, entryCount, truncated }: LogStatusBarProps) {
  return (
    <div className="log-status-bar panel" data-testid="logs.status-bar">
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Канал</span>
        <strong data-testid="logs.status.channel">{channel?.label ?? "Не выбран"}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Подключение</span>
        <strong data-testid="logs.status.connection">{connected ? "подключено" : "ожидание"}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Записей</span>
        <strong data-testid="logs.status.count">{entryCount}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Снепшот</span>
        <strong data-testid="logs.status.truncated">{truncated ? "обрезан" : "полный"}</strong>
      </div>
    </div>
  );
}
