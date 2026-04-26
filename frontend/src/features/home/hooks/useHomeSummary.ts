import { useQuery } from "@tanstack/react-query";
import { getHomeSummary } from "../../../shared/api/client";
import type { HomeSummary } from "../../../shared/contracts";

const POLL_INTERVAL_MS = 5_000;

export function useHomeSummary() {
  return useQuery<HomeSummary>({
    queryKey: ["home", "summary"],
    queryFn: getHomeSummary,
    refetchInterval: POLL_INTERVAL_MS,
  });
}
