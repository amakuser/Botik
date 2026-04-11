import { useQuery } from "@tanstack/react-query";
import { getTelegramOpsModel } from "../../../shared/api/client";

export function useTelegramOpsModel() {
  return useQuery({
    queryKey: ["telegram-ops-model"],
    queryFn: getTelegramOpsModel,
    refetchInterval: 5_000,
  });
}
