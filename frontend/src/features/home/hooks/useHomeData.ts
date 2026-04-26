import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  getDiagnosticsModel,
  getFuturesReadModel,
  getHealth,
  getModelsReadModel,
  getRuntimeStatus,
  getSpotReadModel,
  getTelegramOpsModel,
  listJobs,
} from "../../../shared/api/client";
import type {
  DiagnosticsSnapshot,
  FuturesReadSnapshot,
  HealthResponse,
  JobSummary,
  ModelsReadSnapshot,
  RuntimeStatusSnapshot,
  SpotReadSnapshot,
  TelegramOpsSnapshot,
} from "../../../shared/contracts";

const POLL_INTERVAL_MS = 5_000;

export interface HomeData {
  health: HealthResponse | undefined;
  runtime: RuntimeStatusSnapshot | undefined;
  spot: SpotReadSnapshot | undefined;
  futures: FuturesReadSnapshot | undefined;
  models: ModelsReadSnapshot | undefined;
  telegram: TelegramOpsSnapshot | undefined;
  diagnostics: DiagnosticsSnapshot | undefined;
  jobs: JobSummary[] | undefined;
}

export interface HomeErrors {
  health: Error | null;
  runtime: Error | null;
  spot: Error | null;
  futures: Error | null;
  models: Error | null;
  telegram: Error | null;
  diagnostics: Error | null;
  jobs: Error | null;
}

export interface HomeRefetch {
  health: () => void;
  runtime: () => void;
  spot: () => void;
  futures: () => void;
  models: () => void;
  telegram: () => void;
  diagnostics: () => void;
  jobs: () => void;
  all: () => void;
}

export interface UseHomeDataResult {
  data: HomeData;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  isAllError: boolean;
  errors: HomeErrors;
  refetch: HomeRefetch;
  generatedAt: string | null;
}

function asError(value: unknown): Error | null {
  if (value === null || value === undefined) return null;
  if (value instanceof Error) return value;
  return new Error(String(value));
}

function pickGeneratedAt(
  queries: Array<UseQueryResult<{ generated_at?: string } | undefined>>,
): string | null {
  for (const q of queries) {
    const value = q.data?.generated_at;
    if (typeof value === "string" && value.length > 0) return value;
  }
  return null;
}

export function useHomeData(): UseHomeDataResult {
  const health = useQuery({
    queryKey: ["home", "health"],
    queryFn: getHealth,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const runtime = useQuery({
    queryKey: ["home", "runtime-status"],
    queryFn: getRuntimeStatus,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const spot = useQuery({
    queryKey: ["home", "spot-read-model"],
    queryFn: getSpotReadModel,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const futures = useQuery({
    queryKey: ["home", "futures-read-model"],
    queryFn: getFuturesReadModel,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const models = useQuery({
    queryKey: ["home", "models-read-model"],
    queryFn: getModelsReadModel,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const telegram = useQuery({
    queryKey: ["home", "telegram-ops"],
    queryFn: getTelegramOpsModel,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const diagnostics = useQuery({
    queryKey: ["home", "diagnostics"],
    queryFn: getDiagnosticsModel,
    refetchInterval: POLL_INTERVAL_MS,
  });
  const jobs = useQuery({
    queryKey: ["home", "jobs-list"],
    queryFn: listJobs,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const data: HomeData = {
    health: health.data,
    runtime: runtime.data,
    spot: spot.data,
    futures: futures.data,
    models: models.data,
    telegram: telegram.data,
    diagnostics: diagnostics.data,
    jobs: jobs.data,
  };

  const errors: HomeErrors = {
    health: asError(health.error),
    runtime: asError(runtime.error),
    spot: asError(spot.error),
    futures: asError(futures.error),
    models: asError(models.error),
    telegram: asError(telegram.error),
    diagnostics: asError(diagnostics.error),
    jobs: asError(jobs.error),
  };

  const all = [health, runtime, spot, futures, models, telegram, diagnostics, jobs];
  const isLoading = all.every((q) => q.isLoading);
  const isFetching = all.some((q) => q.isFetching);
  const isError = all.some((q) => q.isError);
  const isAllError = all.every((q) => q.isError);

  const refetch: HomeRefetch = {
    health: () => {
      void health.refetch();
    },
    runtime: () => {
      void runtime.refetch();
    },
    spot: () => {
      void spot.refetch();
    },
    futures: () => {
      void futures.refetch();
    },
    models: () => {
      void models.refetch();
    },
    telegram: () => {
      void telegram.refetch();
    },
    diagnostics: () => {
      void diagnostics.refetch();
    },
    jobs: () => {
      void jobs.refetch();
    },
    all: () => {
      void Promise.all(all.map((q) => q.refetch()));
    },
  };

  const generatedAt = pickGeneratedAt([
    runtime as UseQueryResult<{ generated_at?: string } | undefined>,
    spot as UseQueryResult<{ generated_at?: string } | undefined>,
    futures as UseQueryResult<{ generated_at?: string } | undefined>,
    models as UseQueryResult<{ generated_at?: string } | undefined>,
    telegram as UseQueryResult<{ generated_at?: string } | undefined>,
    diagnostics as UseQueryResult<{ generated_at?: string } | undefined>,
  ]);

  return {
    data,
    isLoading,
    isFetching,
    isError,
    isAllError,
    errors,
    refetch,
    generatedAt,
  };
}
