// "Works" / "Needs plugin" / "Next play only" / "Not possible on Plex",
// with the reason in a popover (tap or hover).
import * as RPopover from "@radix-ui/react-popover";
import { badgeFor, type FeatureInfo, type ServerType, SERVER_NAMES } from "../lib/capabilities";

export function CapabilityBadge({ server, info, plugin = false }: { server: ServerType; info?: FeatureInfo; plugin?: boolean }) {
  if (!info) return null;
  const { label, tone } = badgeFor(info.level, server, plugin);
  const cls = tone === "neutral" ? "badge" : `badge badge-${tone}`;
  return (
    <RPopover.Root>
      <RPopover.Trigger asChild>
        <button type="button" className={cls} aria-label={`${SERVER_NAMES[server]}: ${label}. Why?`}>
          {SERVER_NAMES[server]}: {label}
        </button>
      </RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content className="popover" sideOffset={6}>
          {info.note}
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  );
}
