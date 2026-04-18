import { useQuery } from "@tanstack/react-query";
import { getSettingsSnapshot } from "../../../shared/api/client";

export function useSettingsModel() {
  return useQuery({
    queryKey: ["settings-snapshot"],
    queryFn: getSettingsSnapshot,
    refetchInterval: 30_000,
  });
}
