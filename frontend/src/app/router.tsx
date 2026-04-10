import { createBrowserRouter } from "react-router-dom";
import { HealthRoute } from "./routes/health-route";
import { JobsRoute } from "./routes/jobs-route";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <HealthRoute />,
  },
  {
    path: "/jobs",
    element: <JobsRoute />,
  },
]);
