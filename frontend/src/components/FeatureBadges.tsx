// Shows what an option does on each media server (CONTRACTS §6).
import { pluginWorking, useCapabilities, type Feature, type ServerType } from "../lib/capabilities";
import { useServerSummary } from "../lib/servers";
import { CapabilityBadge } from "./CapabilityBadge";

interface Props {
  feature: Feature;
  /** Only these servers (for options that only exist on some, like rules). */
  only?: ServerType[];
}

export function FeatureBadges({ feature, only }: Props) {
  const caps = useCapabilities();
  const { connected } = useServerSummary();
  if (!caps.data) return null;
  const servers = caps.data.servers
    .filter((s) => (connected.length ? connected.includes(s.type) : true))
    .filter((s) => (only ? only.includes(s.type) : true));
  if (!servers.length) return null;
  return (
    <span className="chips feature-badges">
      {servers.map((s) => (
        <CapabilityBadge key={s.type} server={s.type} info={s.features[feature]} plugin={pluginWorking(s)} />
      ))}
    </span>
  );
}
