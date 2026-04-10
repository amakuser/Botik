import { useEffect, useEffectEvent, useState } from "react";
import { createLogEventSource } from "../../../shared/api/client";
import { LogEntry, LogStreamEvent } from "../../../shared/contracts";

interface UseLogStreamOptions {
  channelId: string | null;
  onEntry: (entry: LogEntry) => void;
}

export function useLogStream({ channelId, onEntry }: UseLogStreamOptions) {
  const [connected, setConnected] = useState(false);
  const handleEntry = useEffectEvent(onEntry);

  useEffect(() => {
    if (!channelId) {
      setConnected(false);
      return;
    }

    let eventSource: EventSource | null = null;
    let closed = false;

    createLogEventSource(channelId)
      .then((source) => {
        if (closed) {
          source.close();
          return;
        }

        eventSource = source;
        setConnected(true);
        source.addEventListener("log-entry", (event) => {
          const payload = JSON.parse(event.data) as LogStreamEvent;
          handleEntry(payload.entry);
        });
        source.onerror = () => {
          setConnected(false);
        };
      })
      .catch(() => {
        setConnected(false);
      });

    return () => {
      closed = true;
      setConnected(false);
      eventSource?.close();
    };
  }, [channelId, handleEntry]);

  return { connected };
}
