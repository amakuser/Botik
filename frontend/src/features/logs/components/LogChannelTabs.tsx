import { LogChannel } from "../../../shared/contracts";

interface LogChannelTabsProps {
  channels: LogChannel[];
  selectedChannelId: string | null;
  onSelect: (channelId: string) => void;
}

export function LogChannelTabs({ channels, selectedChannelId, onSelect }: LogChannelTabsProps) {
  return (
    <div className="log-channel-tabs" role="tablist" aria-label="Log channels">
      {channels.map((channel) => (
        <button
          key={channel.channel_id}
          type="button"
          role="tab"
          aria-selected={selectedChannelId === channel.channel_id}
          className={selectedChannelId === channel.channel_id ? "log-channel-tabs__button is-selected" : "log-channel-tabs__button"}
          onClick={() => onSelect(channel.channel_id)}
          data-testid={`logs.channel.${channel.channel_id}`}
        >
          <span className="log-channel-tabs__body">
            <span className="log-channel-tabs__title">{channel.label}</span>
            <span className="log-channel-tabs__source">{channel.source_kind}</span>
          </span>
          <span className={channel.available ? "status-chip" : "status-chip is-failed"}>{channel.available ? "онлайн" : "офлайн"}</span>
        </button>
      ))}
    </div>
  );
}
