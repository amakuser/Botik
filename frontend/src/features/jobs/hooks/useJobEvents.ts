import { useEffect, useState } from "react";
import { createEventSource } from "../../../shared/api/client";
import { JobEvent, LogEvent } from "../../../shared/contracts";

export interface JobLogEntry {
  eventId: string;
  timestamp: string;
  jobId: string | null;
  level: string;
  message: string;
}

export interface JobEventSnapshot {
  job_id: string;
  job_type: string;
  state: JobEvent["state"];
  progress: number;
  message?: string | null;
  updated_at: string;
}

export function useJobEvents() {
  const [jobSnapshots, setJobSnapshots] = useState<Record<string, JobEventSnapshot>>({});
  const [logsByJob, setLogsByJob] = useState<Record<string, JobLogEntry[]>>({});

  useEffect(() => {
    let activeSource: EventSource | null = null;
    let cancelled = false;

    void createEventSource().then((source) => {
      if (cancelled) {
        source.close();
        return;
      }

      activeSource = source;

      source.addEventListener("job", (event) => {
        const payload = JSON.parse(event.data) as JobEvent;
        setJobSnapshots((current) => ({
          ...current,
          [payload.job_id]: {
            job_id: payload.job_id,
            job_type: payload.job_type,
            state: payload.state,
            progress: payload.progress,
            message: payload.message,
            updated_at: payload.timestamp,
          },
        }));
      });

      source.addEventListener("log", (event) => {
        const payload = JSON.parse(event.data) as LogEvent;
        if (!payload.job_id) {
          return;
        }

        setLogsByJob((current) => {
          const next = current[payload.job_id] ?? [];
          const entry: JobLogEntry = {
            eventId: payload.event_id,
            timestamp: payload.timestamp,
            jobId: payload.job_id,
            level: payload.level,
            message: payload.message,
          };
          return {
            ...current,
            [payload.job_id]: [...next, entry].slice(-48),
          };
        });
      });
    });

    return () => {
      cancelled = true;
      activeSource?.close();
    };
  }, []);

  return {
    jobSnapshots,
    logsByJob,
  };
}
