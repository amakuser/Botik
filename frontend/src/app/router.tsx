import { createBrowserRouter } from "react-router-dom";
import { AnalyticsRoute } from "./routes/analytics-route";
import { DiagnosticsRoute } from "./routes/diagnostics-route";
import { ModelsRoute } from "./routes/models-route";
import { HealthRoute } from "./routes/health-route";
import { FuturesRoute } from "./routes/futures-route";
import { JobsRoute } from "./routes/jobs-route";
import { LogsRoute } from "./routes/logs-route";
import { RuntimeRoute } from "./routes/runtime-route";
import { SpotRoute } from "./routes/spot-route";
import { TelegramRoute } from "./routes/telegram-route";

export const router = createBrowserRouter([
  {
    path: "/",
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
]);
