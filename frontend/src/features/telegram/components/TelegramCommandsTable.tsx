import { TelegramCommandEntry } from "../../../shared/contracts";

interface TelegramCommandsTableProps {
  commands: TelegramCommandEntry[];
}

export function TelegramCommandsTable({ commands }: TelegramCommandsTableProps) {
  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Command</th>
            <th>Status</th>
            <th>Chat</th>
            <th>User</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {commands.length === 0 ? (
            <tr>
              <td colSpan={5}>No recent Telegram commands.</td>
            </tr>
          ) : (
            commands.map((command, index) => (
              <tr key={`${command.command}-${command.ts ?? index}`} data-testid={`telegram.command.${index}`}>
                <td>{command.command}</td>
                <td>{command.status}</td>
                <td>{command.chat_id_masked ?? "-"}</td>
                <td>{command.username ?? "-"}</td>
                <td>{command.ts ? new Date(command.ts).toLocaleString() : "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
