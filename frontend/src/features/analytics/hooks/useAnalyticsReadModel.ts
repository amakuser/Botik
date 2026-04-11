import { useQuery } from "@tanstack/react-query";
import { getAnalyticsReadModel } from "../../../shared/api/client";

export function useAnalyticsReadModel() {
  return useQuery({
    queryKey: ["analytics-read-model"],
    queryFn: getAnalyticsReadModel,
    refetchInterval: 5_000,
  });
}
