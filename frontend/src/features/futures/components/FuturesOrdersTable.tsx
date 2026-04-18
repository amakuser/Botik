import type { FuturesOpenOrder } from "../../../shared/contracts";

interface FuturesOrdersTableProps {
  orders: FuturesOpenOrder[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

export function FuturesOrdersTable({ orders }: FuturesOrdersTableProps) {
  if (orders.length === 0) {
    return <p className="panel-muted surface-table-empty">Активных фьючерсных ордеров нет.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.orders.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Символ</th>
            <th>Сторона</th>
            <th>Тип</th>
            <th>Цена</th>
            <th>Кол-во</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr
              key={order.order_link_id ?? order.order_id ?? `${order.symbol}:${order.updated_at_utc}`}
              data-testid={`futures.order.${order.symbol}`}
            >
              <td className="surface-table__primary">
                <div className="surface-table__stack">
                  <strong>{order.symbol}</strong>
                  <span className="panel-muted">{order.strategy_owner ?? "unassigned strategy"}</span>
                </div>
              </td>
              <td>
                <span className={order.side === "Buy" ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {order.side ?? "n/a"}
                </span>
              </td>
              <td>
                <div className="surface-table__stack">
                  <strong>{order.order_type ?? "n/a"}</strong>
                  <span className="panel-muted">
                    {order.reduce_only ? "reduce-only" : "стандартный"} · {order.time_in_force ?? "n/a"}
                  </span>
                </div>
              </td>
              <td>{formatNumber(order.price, 2)}</td>
              <td>{formatNumber(order.qty, 4)}</td>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-badge surface-badge--soft">{order.status}</span>
                  <span className="panel-muted">{order.close_on_trigger ? "закрытие по триггеру" : "без триггера"}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
