import { createBrowserRouter } from "react-router-dom";
import { HealthRoute } from "./routes/health-route";
import { JobsRoute } from "./routes/jobs-route";
import { LogsRoute } from "./routes/logs-route";

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
]);
