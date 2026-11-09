// "Is it working?" One line per media server: connected, or what's wrong and a fix button.
import { CheckCircle2, AlertTriangle, PauseCircle, Server } from "lucide-react";
import { useMediaServers } from "../../lib/mediaServers";
import { ButtonLink } from "../../components/Button";
import { EmptyState, ErrorNotice, Loading } from "../../components/Notice";

export function ServerHealth() {
  const list = useMediaServers(true);
  if (list.isLoading) return <Loading label="Checking your media servers…" />;
  if (list.isError) return <ErrorNotice error={list.error} onRetry={() => list.refetch()} />;
  const servers = list.data ?? [];
  if (!servers.length) {
    return (
      <EmptyState
        icon={<Server size={36} />}
        title="No media server connected yet"
        action={<ButtonLink to="/servers" variant="primary">Connect a media server</ButtonLink>}
      >
        Connect Plex, Jellyfin or Emby so Prerolls Max can tell it which intro to play.
      </EmptyState>
    );
  }
  return (
    <ul className="list">
      {servers.map((s) => {
        const ok = Boolean(s.status?.connected);
        const apply = s.enabled && s.last_apply && s.last_apply.state !== "ok" ? s.last_apply : null;
        const line = !s.enabled
          ? "Switched off. Prerolls Max leaves its intros alone."
          : ok
            ? apply?.message ?? `Connected at ${s.url}`
            : s.status?.message ?? `Prerolls Max can't reach ${s.name} right now.`;
        const good = !s.enabled || (ok && !apply);
        return (
          <li key={s.id} className={`status-row ${good ? "ok" : "bad"}`}>
            {!s.enabled ? (
              <PauseCircle size={24} className="muted" aria-hidden="true" />
            ) : good ? (
              <CheckCircle2 size={24} className="status-ok" aria-hidden="true" />
            ) : (
              <AlertTriangle size={24} className="status-bad" aria-hidden="true" />
            )}
            <div className="grow">
              <strong>{s.name}</strong> <span className="muted small">({s.type_label})</span>
              <span className="visually-hidden">{!s.enabled ? ": switched off" : good ? ": connected" : ": has a problem"}</span>
              <div className="muted small server-url">{line}</div>
            </div>
            {!good && (
              <ButtonLink to="/servers" size="sm" variant="primary">
                Fix it
              </ButtonLink>
            )}
          </li>
        );
      })}
    </ul>
  );
}
