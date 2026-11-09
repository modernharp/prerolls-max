// What played: recent plays, most and least played, never played, and plays
// by server, person and app. History can be cleared (admins).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { plural } from "../../lib/format";
import { statsKeys, useNeverPlayed, useRecentPlays, useStatsSummary, useTopPlays, type StatsFilters } from "../../lib/stats";
import { PageHeader } from "../../components/HelpPanel";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { Select } from "../../components/Select";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { useToast } from "../../components/Toast";
import { CountBars, PlaysTable, TopList, serverName } from "./StatsParts";

const DAYS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "365", label: "Last year" },
];
const SERVERS = [
  { value: "all", label: "Every server" },
  { value: "plex", label: "Plex" },
  { value: "jellyfin", label: "Jellyfin" },
  { value: "emby", label: "Emby" },
];

export default function StatsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [days, setDays] = useState("30");
  const [server, setServer] = useState("all");
  const [clearing, setClearing] = useState(false);
  const filters: StatsFilters = { days: Number(days), server: server === "all" ? "" : server, user: "" };
  const summary = useStatsSummary(filters.days);
  const recent = useRecentPlays(filters);
  const most = useTopPlays(filters, "most");
  const least = useTopPlays(filters, "least");
  const never = useNeverPlayed(filters.days);

  const clear = async () => {
    const res = await api.del<{ removed: number }>("/api/stats");
    await queryClient.invalidateQueries({ queryKey: statsKeys.all });
    await queryClient.invalidateQueries({ queryKey: statsKeys.health });
    toast({ tone: "success", title: "Play history cleared", description: `${plural(res.removed, "entry", "entries")} removed.` });
  };

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="What Played"
        description="Which intros played, before what, for whom and on which app."
        helpSlug="play-history"
        actions={
          <Button variant="danger-outline" icon={<Trash2 size={18} aria-hidden="true" />} onClick={() => setClearing(true)}>
            Clear history
          </Button>
        }
      />
      <div className="row section-gap">
        <span className="muted small">Plays are counted on:</span>
        <FeatureBadges feature="play_history" />
      </div>
      {s && !s.history_enabled && (
        <Notice tone="warning" title="Play history is off">
          New plays aren't being recorded. Turn it on in <Link to="/settings#playback">Settings, Playback</Link>.
        </Notice>
      )}
      <div className="toolbar">
        <div className="toolbar-select">
          <Select label={<span className="visually-hidden">Time</span>} value={days} onChange={setDays} options={DAYS} />
        </div>
        <div className="toolbar-select">
          <Select label={<span className="visually-hidden">Server</span>} value={server} onChange={setServer} options={SERVERS} />
        </div>
      </div>

      {summary.isLoading ? (
        <Loading />
      ) : summary.isError ? (
        <ErrorNotice error={summary.error} onRetry={() => summary.refetch()} />
      ) : s && s.total_plays === 0 ? (
        <EmptyState icon={<BarChart3 size={40} />} title="No plays recorded yet">
          Start a movie on a connected media server. Plays show up here within a minute. History is kept for {s.retention_days} days.
        </EmptyState>
      ) : s ? (
        <>
          <div className="stat-grid">
            <section className="card stat-card hero-stat" aria-label="Total plays">
              <span className="hero-number">{s.total_plays}</span>
              <span className="muted">intro {s.total_plays === 1 ? "play" : "plays"} in the last {s.days} days</span>
            </section>
            <CountBars title="By server" counts={s.by_server} rename={serverName} />
            <CountBars title="By person" counts={s.by_user} />
            <CountBars title="By app" counts={s.by_client} />
          </div>
          <div className="stat-grid">
            <TopList title="Played most" items={most.data?.items ?? []} empty="Nothing yet." />
            <TopList title="Played least" items={least.data?.items ?? []} empty="Nothing yet." />
            <section className="card stat-card" aria-label="Never played">
              <h3 className="h4-like">Never played</h3>
              {!never.data?.items.length ? (
                <p className="muted small">Every intro has played at least once.</p>
              ) : (
                <>
                  <p className="muted small">Worth a look: check they're in a collection that plays, or give them a higher "How often".</p>
                  <ul className="rank-list">
                    {never.data.items.slice(0, 10).map((n) => (
                      <li key={n.preroll_id}>
                        <span className="grow">{n.name}</span>
                        <span className="muted small">{n.collections.join(", ") || "No collection"}</span>
                      </li>
                    ))}
                  </ul>
                  {never.data.items.length > 10 && <p className="muted small">And {never.data.items.length - 10} more.</p>}
                </>
              )}
            </section>
          </div>
        </>
      ) : null}

      <section className="section" aria-labelledby="recent-title">
        <h2 id="recent-title">Recent plays</h2>
        {recent.isLoading ? (
          <Loading />
        ) : recent.isError ? (
          <ErrorNotice error={recent.error} onRetry={() => recent.refetch()} />
        ) : !recent.data?.items.length ? (
          <p className="muted">No plays in this time.</p>
        ) : (
          <>
            <PlaysTable plays={recent.data.items} />
            <p className="muted small table-note">{recent.data.note}</p>
          </>
        )}
      </section>

      <ConfirmDialog
        open={clearing}
        onOpenChange={setClearing}
        title="Clear all play history?"
        body={
          <p>
            Every recorded play and missed-intro check is removed. Cooldowns ("don't repeat within") start fresh, so a recently played
            intro may play again soon. This can't be undone.
          </p>
        }
        confirmLabel="Clear history"
        danger
        onConfirm={clear}
      />
    </>
  );
}
