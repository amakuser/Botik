import { useQuery } from "@tanstack/react-query";
import { getFuturesReadModel } from "../../../shared/api/client";

export function useFuturesReadModel() {
  return useQuery({
    queryKey: ["futures-read-model"],
    queryFn: getFuturesReadModel,
    refetchInterval: 5_000,
  });
}
