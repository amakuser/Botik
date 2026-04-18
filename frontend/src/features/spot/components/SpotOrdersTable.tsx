import type { SpotOrder } from "../../../shared/contracts";

interface SpotOrdersTableProps {
  orders: SpotOrder[];
}

function formatQty(value: number) {
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPrice(value: number) {
  return value.toFixed(2);
}

export function SpotOrdersTable({ orders }: SpotOrdersTableProps) {
  if (orders.length === 0) {
    return <p className="panel-muted surface-table-empty">Активных спот-ордеров нет.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.orders.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Символ</th>
            <th>Сторона</th>
            <th>Цена</th>
            <th>Кол-во</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.order_link_id ?? order.order_id ?? `${order.symbol}:${order.updated_at_utc}`} data-testid={`spot.order.${order.symbol}`}>
              <td className="surface-table__primary">{order.symbol}</td>
              <td>
                <span className={order.side === "Buy" ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {order.side}
                </span>
              </td>
              <td>{formatPrice(order.price)}</td>
              <td>{formatQty(order.qty)}</td>
              <td>
                <span className="surface-badge surface-badge--soft">{order.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
