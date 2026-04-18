import { useQuery } from "@tanstack/react-query";
import { getOrderbook } from "../../../shared/api/client";

export function useOrderbook(symbol: string, category: string) {
  return useQuery({
    queryKey: ["orderbook", symbol, category],
    queryFn: () => getOrderbook(symbol, category),
    refetchInterval: 20_000,
  });
}
