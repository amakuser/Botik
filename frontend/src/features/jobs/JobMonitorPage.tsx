import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getJob, listJobs, startJob, stopJob } from "../../shared/api/client";
import { JobDetails, JobState, JobSummary } from "../../shared/contracts";
import { AppShell } from "../../shared/ui/AppShell";
import { JobLogPanel } from "./components/JobLogPanel";
import { JobStatusCard } from "./components/JobStatusCard";
import { JobToolbar } from "./components/JobToolbar";
import { useJobEvents } from "./hooks/useJobEvents";

const ACTIVE_STATES: JobState[] = ["queued", "starting", "running", "stopping"];

function toDetails(job: JobSummary, lastError: string | null = null): JobDetails {
  return {
    job_id: job.job_id,
    job_type: job.job_type,
    state: job.state,
    progress: job.progress,
    started_at: null,
    updated_at: job.updated_at,
    exit_code: null,
    last_error: lastError,
    log_stream_id: null,
  };
}

function toSummary(job: JobDetails): JobSummary {
  return {
    job_id: job.job_id,
    job_type: job.job_type,
    state: job.state,
    progress: job.progress,
    updated_at: job.updated_at,
  };
}

export function JobMonitorPage() {
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { jobSnapshots, logsByJob } = useJobEvents();

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 2_000,
  });

  const selectedJobQuery = useQuery({
    queryKey: ["job", selectedJobId],
    queryFn: () => getJob(selectedJobId!),
    enabled: Boolean(selectedJobId),
    refetchInterval: selectedJobId ? 2_000 : false,
  });

  const jobs = (jobsQuery.data ?? []).map((job) => {
    const snapshot = jobSnapshots[job.job_id];
    return snapshot
      ? {
          ...job,
          state: snapshot.state,
          progress: snapshot.progress,
          updated_at: snapshot.updated_at,
        }
      : job;
  });

  useEffect(() => {
    if (selectedJobId) {
      return;
    }

    const latestJob = jobs[0];
    if (latestJob) {
      setSelectedJobId(latestJob.job_id);
    }
  }, [jobs, selectedJobId]);

  const selectedSnapshot = selectedJobId ? jobSnapshots[selectedJobId] : undefined;
  const selectedJob = selectedJobQuery.data
    ? {
        ...selectedJobQuery.data,
        state: selectedSnapshot?.state ?? selectedJobQuery.data.state,
        progress: selectedSnapshot?.progress ?? selectedJobQuery.data.progress,
        updated_at: selectedSnapshot?.updated_at ?? selectedJobQuery.data.updated_at,
      }
    : selectedJobId
      ? (() => {
          const fallback = jobs.find((job) => job.job_id === selectedJobId);
          return fallback ? toDetails(fallback, null) : null;
        })()
      : null;

  const activeJob = jobs.find((job) => ACTIVE_STATES.includes(job.state));
  const logs = selectedJobId ? logsByJob[selectedJobId] ?? [] : [];

  async function handleStart() {
    setActionError(null);
    try {
      const created = await startJob({
        job_type: "sample_data_import",
        payload: {
          sleep_ms: 140,
        },
      });
      setSelectedJobId(created.job_id);
      queryClient.setQueryData<JobSummary[]>(["jobs"], (current) => {
        const next = current ? [...current] : [];
        return [toSummary(created), ...next.filter((job) => job.job_id !== created.job_id)];
      });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["job", created.job_id] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to start the sample data import.");
    }
  }

  async function handleStop() {
    if (!selectedJobId) {
      return;
    }

    setActionError(null);
    try {
      await stopJob(selectedJobId, { reason: "job-monitor-stop" });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["job", selectedJobId] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to stop the selected job.");
    }
  }

  return (
    <AppShell>
      <div className="jobs-layout">
        <div className="jobs-sidebar">
          <JobToolbar
            startDisabled={Boolean(activeJob)}
            stopDisabled={!selectedJob || !ACTIVE_STATES.includes(selectedJob.state)}
            onStart={handleStart}
            onStop={handleStop}
          />

          <section className="panel" aria-labelledby="job-list-title">
            <h2 id="job-list-title">Job History</h2>
            {jobs.length === 0 ? (
              <p className="panel-muted" data-testid="jobs.history.empty">
                No jobs have run yet.
              </p>
            ) : (
              <ol className="jobs-list">
                {jobs.map((job) => (
                  <li key={job.job_id}>
                    <button
                      type="button"
                      className={job.job_id === selectedJobId ? "jobs-list__button is-selected" : "jobs-list__button"}
                      onClick={() => setSelectedJobId(job.job_id)}
                    >
                      <div className="jobs-list__title">{job.job_type}</div>
                      <div className="jobs-list__meta">
                        <span>{job.state}</span>
                        <span>{Math.round(job.progress * 100)}%</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <div className="jobs-main">
          <JobStatusCard job={selectedJob} />
          <JobLogPanel logs={logs} />
          {actionError ? (
            <section className="panel">
              <h2>Action Error</h2>
              <p className="inline-error" data-testid="jobs.action-error">
                {actionError}
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </AppShell>
  );
}
