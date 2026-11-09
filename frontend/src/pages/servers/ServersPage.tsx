// Media Servers: every Plex, Jellyfin and Emby server, grouped by type.
// Several of one type are fine (a living room and a bedroom Jellyfin);
// "Add a server" asks which kind, then shows the usual connect form.
import { useState } from "react";
import { Plus, Server } from "lucide-react";
import { SERVER_TYPES } from "../../lib/servers";
import { useMediaServers, type MediaServer } from "../../lib/mediaServers";
import { FEATURE_LABELS, SERVER_NAMES, pluginWorking, useCapabilities, type Feature, type ServerType } from "../../lib/capabilities";
import { PageHeader } from "../../components/HelpPanel";
import { Button } from "../../components/Button";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../components/Notice";
import { CapabilityBadge } from "../../components/CapabilityBadge";
import { ServerCard } from "./ServerCard";
import { NexrollBanner } from "../../components/NexrollBanner";
import { AddServerDialog, EditServerDialog } from "./ServerDialogs";

const KEY_FEATURES: Feature[] = ["random", "sequence", "episodes", "per_user", "genre_rules", "trailers"];

function WhatItCanDo({ type }: { type: ServerType }) {
  const caps = useCapabilities();
  const serverCaps = caps.data?.servers.find((s) => s.type === type);
  const features = serverCaps?.features ?? {};
  return (
    <>
      <details className="details-toggle">
        <summary>What {SERVER_NAMES[type]} can do</summary>
        <ul className="feature-list">
          {KEY_FEATURES.map((f) => (
            <li key={f}>
              <span>{FEATURE_LABELS[f]}</span>
              <CapabilityBadge server={type} info={features[f]} plugin={pluginWorking(serverCaps)} />
            </li>
          ))}
        </ul>
      </details>
      {features.client_notes && (
        <details className="details-toggle">
          <summary>Apps that skip intros on {SERVER_NAMES[type]}</summary>
          <Notice tone="warning">{features.client_notes.note}</Notice>
        </details>
      )}
    </>
  );
}

export default function ServersPage() {
  const list = useMediaServers();
  const checked = useMediaServers(true);
  const caps = useCapabilities();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<MediaServer | null>(null);
  const servers = (list.data ?? []).map((s) => ({ ...s, status: checked.data?.find((c) => c.id === s.id)?.status }));
  const add = (
    <Button variant="primary" icon={<Plus size={18} aria-hidden="true" />} onClick={() => setAdding(true)}>
      Add a server
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Media Servers"
        description="The servers that play your intros. Add as many as you have, of any kind."
        helpSlug="devices"
        actions={servers.length ? add : undefined}
      />
      <NexrollBanner />
      {caps.data?.builtin && (
        <p className="muted small section-gap">What each server can do is based on their published features as of November 2026.</p>
      )}
      {list.isLoading ? (
        <Loading label="Loading your media servers…" />
      ) : list.isError ? (
        <ErrorNotice error={list.error} onRetry={() => list.refetch()} />
      ) : !servers.length ? (
        <EmptyState icon={<Server size={36} />} title="No media server yet" action={add}>
          Add Plex, Jellyfin or Emby so Prerolls Max can tell it which intro to play.
        </EmptyState>
      ) : (
        SERVER_TYPES.filter((t) => servers.some((s) => s.type === t)).map((type) => {
          const mine = servers.filter((s) => s.type === type);
          return (
            <section key={type} className="server-group" aria-labelledby={`group-${type}`}>
              <div className="row-between">
                <h2 id={`group-${type}`}>
                  {SERVER_NAMES[type]} <span className="muted small">({mine.length})</span>
                </h2>
              </div>
              {type === "plex" && mine.filter((s) => s.enabled).length > 1 && (
                <p className="muted small">
                  Every Plex server that's switched on gets the same intros, each through its own folder mapping.
                </p>
              )}
              <div className="card-grid">
                {mine.map((s) => (
                  <ServerCard key={s.id} server={s} onEdit={() => setEditing(s)} />
                ))}
              </div>
              <WhatItCanDo type={type} />
            </section>
          );
        })
      )}
      <AddServerDialog open={adding} onOpenChange={setAdding} servers={list.data ?? []} />
      {editing && <EditServerDialog key={editing.id} server={editing} servers={list.data ?? []} onClose={() => setEditing(null)} />}
    </>
  );
}
