import { useQuery } from "@tanstack/react-query";
import { getDiagnosticsModel } from "../../../shared/api/client";

export function useDiagnosticsModel() {
  return useQuery({
    queryKey: ["diagnostics-model"],
    queryFn: getDiagnosticsModel,
    refetchInterval: 5_000,
  });
}
