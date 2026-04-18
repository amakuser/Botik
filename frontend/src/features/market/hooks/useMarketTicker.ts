import { useQuery } from "@tanstack/react-query";
import { getMarketTicker } from "../../../shared/api/client";

export function useMarketTicker(symbols?: string[]) {
  return useQuery({
    queryKey: ["market-ticker", symbols],
    queryFn: () => getMarketTicker(symbols),
    refetchInterval: 5_000,
  });
}
