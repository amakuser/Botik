import { useQuery } from "@tanstack/react-query";
import { getModelsReadModel } from "../../../shared/api/client";

export function useModelsReadModel() {
  return useQuery({
    queryKey: ["models-read-model"],
    queryFn: getModelsReadModel,
    refetchInterval: 5_000,
  });
}
