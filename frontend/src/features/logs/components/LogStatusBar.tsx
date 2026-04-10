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
      <div>
        <strong>Channel:</strong> <span data-testid="logs.status.channel">{channel?.label ?? "None selected"}</span>
      </div>
      <div>
        <strong>Connection:</strong> <span data-testid="logs.status.connection">{connected ? "connected" : "idle"}</span>
      </div>
      <div>
        <strong>Entries:</strong> <span data-testid="logs.status.count">{entryCount}</span>
      </div>
      <div>
        <strong>Snapshot:</strong> <span data-testid="logs.status.truncated">{truncated ? "truncated" : "complete"}</span>
      </div>
    </div>
  );
}
