import type { SpotBalance } from "../../../shared/contracts";

interface SpotBalancesTableProps {
  balances: SpotBalance[];
}

function formatQty(value: number) {
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

export function SpotBalancesTable({ balances }: SpotBalancesTableProps) {
  if (balances.length === 0) {
    return <p className="panel-muted surface-table-empty">Балансы спот аккаунта недоступны.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.balances.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Актив</th>
            <th>Свободно</th>
            <th>Заблокировано</th>
            <th>Всего</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          {balances.map((balance) => (
            <tr key={balance.asset} data-testid={`spot.balance.${balance.asset}`}>
              <td className="surface-table__primary">{balance.asset}</td>
              <td>{formatQty(balance.free_qty)}</td>
              <td>{formatQty(balance.locked_qty)}</td>
              <td>{formatQty(balance.total_qty)}</td>
              <td>
                <span className="surface-badge">{balance.source_of_truth ?? "unknown"}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
