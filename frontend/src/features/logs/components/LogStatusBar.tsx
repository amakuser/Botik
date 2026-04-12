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
        <span className="log-status-bar__label">Channel</span>
        <strong data-testid="logs.status.channel">{channel?.label ?? "None selected"}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Connection</span>
        <strong data-testid="logs.status.connection">{connected ? "connected" : "idle"}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Entries</span>
        <strong data-testid="logs.status.count">{entryCount}</strong>
      </div>
      <div className="log-status-bar__item">
        <span className="log-status-bar__label">Snapshot</span>
        <strong data-testid="logs.status.truncated">{truncated ? "truncated" : "complete"}</strong>
      </div>
    </div>
  );
}
