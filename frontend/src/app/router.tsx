import { createBrowserRouter } from "react-router-dom";
import { AnalyticsRoute } from "./routes/analytics-route";
import { BacktestRoute } from "./routes/backtest-route";
import { DiagnosticsRoute } from "./routes/diagnostics-route";
import { MarketRoute } from "./routes/market-route";
import { ModelsRoute } from "./routes/models-route";
import { HealthRoute } from "./routes/health-route";
import { HomeRoute } from "./routes/home-route";
import { FuturesRoute } from "./routes/futures-route";
import { JobsRoute } from "./routes/jobs-route";
import { LogsRoute } from "./routes/logs-route";
import { OrderbookRoute } from "./routes/orderbook-route";
import { RuntimeRoute } from "./routes/runtime-route";
import { SettingsRoute } from "./routes/settings-route";
import { SpotRoute } from "./routes/spot-route";
import { TelegramRoute } from "./routes/telegram-route";
import { UiLabPage } from "../features/ui-lab/UiLabPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <HomeRoute />,
  },
  {
    path: "/health",
    element: <HealthRoute />,
  },
  {
    path: "/jobs",
    element: <JobsRoute />,
  },
  {
    path: "/logs",
    element: <LogsRoute />,
  },
  {
    path: "/runtime",
    element: <RuntimeRoute />,
  },
  {
    path: "/spot",
    element: <SpotRoute />,
  },
  {
    path: "/futures",
    element: <FuturesRoute />,
  },
  {
    path: "/telegram",
    element: <TelegramRoute />,
  },
  {
    path: "/analytics",
    element: <AnalyticsRoute />,
  },
  {
    path: "/models",
    element: <ModelsRoute />,
  },
  {
    path: "/diagnostics",
    element: <DiagnosticsRoute />,
  },
  {
    path: "/settings",
    element: <SettingsRoute />,
  },
  {
    path: "/market",
    element: <MarketRoute />,
  },
  {
    path: "/orderbook",
    element: <OrderbookRoute />,
  },
  {
    path: "/backtest",
    element: <BacktestRoute />,
  },
  {
    path: "/ui-lab",
    element: <UiLabPage />,
  },
]);
