import { TelegramCommandEntry } from "../../../shared/contracts";

interface TelegramCommandsTableProps {
  commands: TelegramCommandEntry[];
}

export function TelegramCommandsTable({ commands }: TelegramCommandsTableProps) {
  if (commands.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>Последних команд Telegram нет.</strong>
        <p className="panel-muted">История команд появится после записи активности.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Команда</th>
            <th>Статус</th>
            <th>Чат</th>
            <th>Пользователь</th>
            <th>Когда</th>
          </tr>
        </thead>
        <tbody>
          {commands.map((command, index) => (
            <tr key={`${command.command}-${command.ts ?? index}`} data-testid={`telegram.command.${index}`}>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{command.command}</span>
                  <span className="panel-muted">{command.args || "Без аргументов"}</span>
                </div>
              </td>
              <td>
                <span className={command.status === "ok" ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--soft"}>
                  {command.status}
                </span>
              </td>
              <td>{command.chat_id_masked ?? "-"}</td>
              <td>
                <div className="surface-table__stack">
                  <span>{command.username ?? "-"}</span>
                  <span className="panel-muted">{command.source}</span>
                </div>
              </td>
              <td>{command.ts ? new Date(command.ts).toLocaleString() : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
