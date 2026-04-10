import { createBrowserRouter } from "react-router-dom";
import { HealthRoute } from "./routes/health-route";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <HealthRoute />,
  },
]);
