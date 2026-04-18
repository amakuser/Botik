import { NavLink } from "react-router-dom";
import { PropsWithChildren } from "react";
import { DesktopFrame } from "./DesktopFrame";

type NavItem = {
  to: string;
  label: string;
  end?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Основное",
    items: [
      { to: "/", label: "Состояние системы", end: true },
      { to: "/jobs", label: "Мониторинг задач" },
      { to: "/logs", label: "Логи" },
      { to: "/runtime", label: "Управление рантаймом" },
    ],
  },
  {
    label: "Данные",
    items: [
      { to: "/spot", label: "Спот" },
      { to: "/futures", label: "Фьючерсы" },
      { to: "/telegram", label: "Телеграм" },
      { to: "/analytics", label: "PnL / Аналитика" },
      { to: "/models", label: "Модели" },
      { to: "/market", label: "Рынок" },
      { to: "/orderbook", label: "Стакан ордеров" },
      { to: "/diagnostics", label: "Диагностика" },
    ],
  },
  {
    label: "Система",
    items: [
      { to: "/backtest", label: "Бэктест" },
      { to: "/settings", label: "Настройки" },
      { to: "/ui-lab", label: "UI Lab" },
    ],
  },
];

export function AppShell({ children }: PropsWithChildren) {
  return (
    <DesktopFrame>
      <div className="app-shell" data-testid="foundation.app-shell">
        <aside className="app-shell__sidebar">
          <header className="app-shell__header">
            <p className="app-shell__eyebrow">Botik</p>
            <h1>Botik</h1>
            <p className="app-shell__subtitle">
              Торговый бот Bybit — дашборд оператора.
            </p>
          </header>

          <nav className="app-shell__nav" aria-label="Primary">
            {NAV_GROUPS.map((group) => (
              <section key={group.label} className="app-shell__nav-group" aria-labelledby={`nav-group-${group.label}`}>
                <p id={`nav-group-${group.label}`} className="app-shell__nav-group-title">
                  {group.label}
                </p>
                <div className="app-shell__nav-links">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </section>
            ))}
          </nav>
        </aside>

        <main className="app-shell__main">
          <div className="app-shell__content">{children}</div>
        </main>
      </div>
    </DesktopFrame>
  );
}
