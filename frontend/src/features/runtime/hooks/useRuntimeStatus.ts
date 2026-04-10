import { useQuery } from "@tanstack/react-query";
import { getRuntimeStatus } from "../../../shared/api/client";

export function useRuntimeStatus() {
  return useQuery({
    queryKey: ["runtime-status"],
    queryFn: getRuntimeStatus,
    refetchInterval: 3_000,
  });
}
