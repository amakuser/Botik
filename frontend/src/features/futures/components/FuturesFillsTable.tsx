import type { FuturesFill } from "../../../shared/contracts";

interface FuturesFillsTableProps {
  fills: FuturesFill[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

export function FuturesFillsTable({ fills }: FuturesFillsTableProps) {
  if (fills.length === 0) {
    return <p className="panel-muted surface-table-empty">Последних фьючерсных сделок нет.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.fills.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Символ</th>
            <th>Сторона</th>
            <th>Цена</th>
            <th>Кол-во</th>
            <th>Комиссия</th>
          </tr>
        </thead>
        <tbody>
          {fills.map((fill) => (
            <tr key={fill.exec_id} data-testid={`futures.fill.${fill.exec_id}`}>
              <td className="surface-table__primary">{fill.symbol}</td>
              <td>
                <span className={fill.side === "Buy" ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {fill.side}
                </span>
              </td>
              <td>{formatNumber(fill.price, 2)}</td>
              <td>{formatNumber(fill.qty, 4)}</td>
              <td>
                <div className="surface-table__stack">
                  <strong>
                    {fill.exec_fee === null || fill.exec_fee === undefined
                      ? "n/a"
                      : `${fill.exec_fee.toFixed(4)} ${fill.fee_currency ?? ""}`.trim()}
                  </strong>
                  <span className="panel-muted">{fill.is_maker ? "мейкер" : "тейкер"}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
