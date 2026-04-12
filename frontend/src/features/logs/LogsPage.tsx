import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getLogSnapshot, listLogChannels } from "../../shared/api/client";
import { LogChannel, LogEntry } from "../../shared/contracts";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { LogChannelTabs } from "./components/LogChannelTabs";
import { LogStatusBar } from "./components/LogStatusBar";
import { LogViewer } from "./components/LogViewer";
import { useLogStream } from "./hooks/useLogStream";

function mergeEntries(current: LogEntry[], nextEntry: LogEntry): LogEntry[] {
  if (current.some((entry) => entry.entry_id === nextEntry.entry_id)) {
    return current;
  }
  return [...current, nextEntry];
}

export function LogsPage() {
  const channelsQuery = useQuery({
    queryKey: ["logs", "channels"],
    queryFn: listLogChannels,
    refetchInterval: 2_000,
  });

  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [truncated, setTruncated] = useState(false);

  const channels = channelsQuery.data ?? [];
  const liveChannelCount = channels.filter((channel) => channel.available).length;
  const offlineChannelCount = channels.length - liveChannelCount;
  const selectedChannel = useMemo<LogChannel | null>(
    () => channels.find((channel) => channel.channel_id === selectedChannelId) ?? null,
    [channels, selectedChannelId],
  );

  useEffect(() => {
    if (selectedChannelId && channels.some((channel) => channel.channel_id === selectedChannelId)) {
      return;
    }

    const preferred = channels.find((channel) => channel.available) ?? channels[0];
    if (preferred) {
      setSelectedChannelId(preferred.channel_id);
    }
  }, [channels, selectedChannelId]);

  const snapshotQuery = useQuery({
    queryKey: ["logs", "snapshot", selectedChannelId],
    queryFn: () => getLogSnapshot(selectedChannelId!),
    enabled: Boolean(selectedChannelId),
    refetchInterval: selectedChannel?.available ? 4_000 : false,
  });

  useEffect(() => {
    if (!snapshotQuery.data || snapshotQuery.data.channel !== selectedChannelId) {
      return;
    }
    setEntries(snapshotQuery.data.entries);
    setTruncated(snapshotQuery.data.truncated);
  }, [selectedChannelId, snapshotQuery.data]);

  const { connected } = useLogStream({
    channelId: selectedChannel?.available ? selectedChannelId : null,
    onEntry: (entry) => {
      setEntries((current) => mergeEntries(current, entry));
    },
  });

  return (
    <AppShell>
      <div className="app-route logs-page">
        <PageIntro
          eyebrow="Observability"
          title="Unified Logs"
          description="Read-only recent and live logs for the primary stack, job flows, and desktop shell artifacts."
          meta={
            <>
              <p className="status-caption">Live channels: {liveChannelCount}</p>
              <p className="status-caption">Offline channels: {offlineChannelCount}</p>
              <p className="status-caption">Selected: {selectedChannel?.label ?? "none"}</p>
            </>
          }
        />

        <div className="logs-layout">
          <section className="panel logs-channel-panel">
            <SectionHeading title="Channels" description="Approved first-slice log channels with bounded snapshot and live append behavior." />
            <LogChannelTabs channels={channels} selectedChannelId={selectedChannelId} onSelect={setSelectedChannelId} />
          </section>

          <section className="logs-main">
            <LogStatusBar channel={selectedChannel} connected={connected} entryCount={entries.length} truncated={truncated} />
            <LogViewer
              entries={entries}
              emptyMessage={
                selectedChannel?.available
                  ? "No log entries have been captured for this channel yet."
                  : "This channel is not currently available in this runtime."
              }
            />
            {channelsQuery.isError || snapshotQuery.isError ? (
              <section className="panel">
                <h2>Logs Error</h2>
                <p className="inline-error" data-testid="logs.error">
                  Failed to load the selected log channel.
                </p>
              </section>
            ) : null}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
