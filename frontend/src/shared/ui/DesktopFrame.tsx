import { getCurrentWindow } from "@tauri-apps/api/window";
import { PropsWithChildren, useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { isDesktopRuntime } from "../host";
import { loadRuntimeConfig } from "../config";

function useBotActive(): boolean {
  const [active, setActive] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const cfg = await loadRuntimeConfig();
        const url = new URL("/runtime-status", cfg.appServiceUrl);
        const res = await fetch(url, { headers: { "x-botik-session-token": cfg.sessionToken } });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { runtimes?: { state: string }[] };
        if (!cancelled) setActive(data?.runtimes?.some(r => r.state === "running") ?? false);
      } catch {
        /* offline — stay idle */
      }
    }

    void check();
    const timer = setInterval(() => void check(), 3_000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  return active;
}

type RouteChromeMeta = {
  section: string;
  title: string;
  note: string;
};

const ROUTE_CHROME_META: Record<string, RouteChromeMeta> = {
  "/": {
    section: "Система",
    title: "Состояние системы",
    note: "Инициализация, здоровье и готовность компонентов.",
  },
  "/jobs": {
    section: "Операции",
    title: "Мониторинг задач",
    note: "Активные задачи, история выполнения и контекст запуска.",
  },
  "/logs": {
    section: "Наблюдение",
    title: "Логи",
    note: "Живые каналы логов текущего стека.",
  },
  "/runtime": {
    section: "Управление",
    title: "Управление рантаймом",
    note: "Состояние спот и фьючерс рантаймов с управлением.",
  },
  "/spot": {
    section: "Данные",
    title: "Спот",
    note: "Балансы, холдинги и поток ордеров — только чтение.",
  },
  "/futures": {
    section: "Данные",
    title: "Фьючерсы",
    note: "Позиции, защита и активность фьючерсного аккаунта.",
  },
  "/telegram": {
    section: "Операции",
    title: "Телеграм",
    note: "Здоровье бота, статус доставки и последняя активность.",
  },
  "/analytics": {
    section: "Аналитика",
    title: "PnL / Аналитика",
    note: "Ключевые метрики производительности и закрытые сделки.",
  },
  "/models": {
    section: "Модели",
    title: "Модели",
    note: "Готовность реестра, состояние обучения и управление.",
  },
  "/diagnostics": {
    section: "Диагностика",
    title: "Диагностика",
    note: "Конфигурация, пути и предупреждения совместимости.",
  },
  "/settings": {
    section: "Система",
    title: "Настройки",
    note: "API ключи, подключение и конфигурация окружения.",
  },
  "/market": {
    section: "Рыночные данные",
    title: "Рынок",
    note: "Цены в реальном времени и статистика рынка Bybit за 24ч.",
  },
  "/orderbook": {
    section: "Рыночные данные",
    title: "Стакан ордеров",
    note: "Глубина стакана в реальном времени по выбранному инструменту.",
  },
  "/backtest": {
    section: "Стратегия",
    title: "Бэктест",
    note: "Историческая симуляция стратегии на локальных OHLCV данных.",
  },
};

function getRouteChromeMeta(pathname: string): RouteChromeMeta {
  if (pathname === "/") {
    return ROUTE_CHROME_META["/"];
  }

  const match = Object.entries(ROUTE_CHROME_META).find(([path]) => path !== "/" && pathname.startsWith(path));
  return match ? match[1] : ROUTE_CHROME_META["/"];
}

async function runWindowAction(action: () => Promise<void>) {
  try {
    await action();
  } catch (error) {
    console.error("Desktop window action failed", error);
  }
}

export function DesktopFrame({ children }: PropsWithChildren) {
  const desktop = isDesktopRuntime();
  const location = useLocation();
  const appWindow = useMemo(
    () => (desktop && typeof window !== "undefined" && "__TAURI_INTERNALS__" in window ? getCurrentWindow() : null),
    [desktop],
  );
  const [isMaximized, setIsMaximized] = useState(false);
  const routeMeta = useMemo(() => getRouteChromeMeta(location.pathname), [location.pathname]);
  const botActive = useBotActive();

  const syncMaximizedState = useCallback(async () => {
    if (!appWindow) {
      return;
    }

    try {
      setIsMaximized(await appWindow.isMaximized());
    } catch (error) {
      console.error("Failed to read desktop maximize state", error);
    }
  }, [appWindow]);

  useEffect(() => {
    if (!appWindow) {
      return;
    }

    let mounted = true;
    let unlisten: (() => void) | undefined;

    const sync = async () => {
      try {
        const nextValue = await appWindow.isMaximized();
        if (mounted) {
          setIsMaximized(nextValue);
        }
      } catch (error) {
        console.error("Failed to sync desktop maximize state", error);
      }
    };

    void sync();
    void appWindow.onResized(() => {
      void sync();
    }).then((listener) => {
      unlisten = listener;
    });

    return () => {
      mounted = false;
      unlisten?.();
    };
  }, [appWindow, syncMaximizedState]);

  const handleToggleMaximize = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(async () => {
      await appWindow.toggleMaximize();
      await syncMaximizedState();
    });
  }, [appWindow, syncMaximizedState]);

  const handleMinimize = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(() => appWindow.minimize());
  }, [appWindow]);

  const handleClose = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(() => appWindow.close());
  }, [appWindow]);

  if (!desktop) {
    return <>{children}</>;
  }

  return (
    <div
      className={isMaximized ? "desktop-frame is-maximized" : "desktop-frame"}
      data-testid="foundation.desktop-frame"
    >
      <header className="desktop-frame__titlebar" data-testid="foundation.desktop-titlebar">

        {/* macOS-style window controls — LEFT */}
        <div className="desktop-frame__window-controls" aria-label="Управление окном" onDoubleClick={handleToggleMaximize}>
          <button
            type="button"
            className="desktop-frame__window-control desktop-frame__window-control--close"
            aria-label="Закрыть"
            onClick={handleClose}
          />
          <button
            type="button"
            className="desktop-frame__window-control desktop-frame__window-control--minimize"
            aria-label="Свернуть"
            onClick={handleMinimize}
          />
          <button
            type="button"
            className="desktop-frame__window-control desktop-frame__window-control--maximize"
            aria-label={isMaximized ? "Восстановить" : "Развернуть"}
            onClick={handleToggleMaximize}
          />
        </div>

        {/* Drag surface — CENTER (brand + status) */}
        <div
          className="desktop-frame__drag-surface"
          data-tauri-drag-region
          onDoubleClick={handleToggleMaximize}
        >
          <div className="desktop-frame__brand-lockup" data-tauri-drag-region>
            <span
              className={botActive ? "desktop-frame__bot-dot desktop-frame__bot-dot--running" : "desktop-frame__bot-dot"}
              title={botActive ? "Бот запущен" : "Бот остановлен"}
            />
            <strong className="desktop-frame__brand">Botik</strong>
            <span className="desktop-frame__bot-state">{botActive ? "Работает" : "Остановлен"}</span>
          </div>
        </div>

        {/* Route context — RIGHT (hidden visually, kept for tests) */}
        <div
          className="desktop-frame__route-context"
          data-tauri-drag-region
          data-testid="foundation.desktop-route-context"
          onDoubleClick={handleToggleMaximize}
        >
          <div className="desktop-frame__route-copy">
            <p className="desktop-frame__route-label">{routeMeta.section}</p>
            <strong className="desktop-frame__route-title">{routeMeta.title}</strong>
            <p className="desktop-frame__route-note">{routeMeta.note}</p>
          </div>
          <span className="desktop-frame__window-state">
            {isMaximized ? "Развёрнуто" : "В окне"}
          </span>
        </div>

      </header>

      <div className="desktop-frame__body">
        <div className="desktop-frame__body-frame">{children}</div>
      </div>
    </div>
  );
}
