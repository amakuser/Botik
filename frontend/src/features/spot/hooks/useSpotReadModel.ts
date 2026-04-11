import { useQuery } from "@tanstack/react-query";
import { getSpotReadModel } from "../../../shared/api/client";

export function useSpotReadModel() {
  return useQuery({
    queryKey: ["spot-read-model"],
    queryFn: getSpotReadModel,
    refetchInterval: 5_000,
  });
}
