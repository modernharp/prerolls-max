// Coming soon from Radarr and Sonarr, the trailers already downloaded, and
// "Get trailers now" with live progress.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, RefreshCw } from "lucide-react";
import { api } from "../../../../lib/api";
import { listWords } from "../../../../lib/scheduleText";
import { formatDateTime, formatDay, plural } from "../../../../lib/format";
import { Button } from "../../../../components/Button";
import { EmptyState, ErrorNotice, Loading, Notice, ProgressBar } from "../../../../components/Notice";
import { ResultNotice, type ActionResult } from "./ResultNotice";
import { SETTINGS_KEY, type DownloadedTrailer, type TrailerSettings, type UpcomingMovie, type UpcomingShow } from "./useTrailers";

interface SyncProgress {
  syncing?: boolean;
  progress?: number;
  status?: string;
}

/** Follows /nexup/sync-progress (server-sent events) while a sync runs. */
function useSyncProgress(active: boolean): SyncProgress | null {
  const [state, setState] = useState<SyncProgress | null>(null);
  useEffect(() => {
    if (!active || typeof EventSource === "undefined") return undefined;
    const source = new EventSource("/nexup/sync-progress");
    source.onmessage = (e) => {
      try {
        setState(JSON.parse(e.data) as SyncProgress);
      } catch {
        // A garbled line is skipped; the next one arrives in a moment.
      }
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [active]);
  return active ? state : null;
}

/** "Radarr 4K didn't answer, so its movies…" / "Radarr and Radarr 4K didn't answer, so their movies…" */
export function missingServers(names: string[], what: "movies" | "shows"): string {
  const whose = names.length === 1 ? "its" : "their";
  return `${listWords(names)} didn't answer, so ${whose} ${what} are missing below.`;
}

export function SyncButton({ settings }: { settings: TrailerSettings }) {
  const queryClient = useQueryClient();
  const withTv = settings.sonarr_connected && settings.sonarr_enabled;
  const sync = useMutation({
    mutationFn: async () => {
      const movies = await api.post<ActionResult>("/nexup/sync", {}, { timeoutMs: 15 * 60_000 });
      const shows = withTv ? await api.post<ActionResult>("/nexup/sonarr/sync", {}, { timeoutMs: 15 * 60_000 }) : null;
      return { movies, shows };
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["downloaded-trailers"] });
      void queryClient.invalidateQueries({ queryKey: ["upcoming"] });
      void queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
    },
  });
  const progress = useSyncProgress(sync.isPending);
  const ready = settings.radarr_connected && Boolean(settings.storage_path);
  return (
    <div className="stack-sm">
      <div className="row">
        <Button variant="primary" icon={<RefreshCw size={18} aria-hidden="true" />} loading={sync.isPending} disabled={!ready} onClick={() => sync.mutate()}>
          Get trailers now
        </Button>
        <span className="muted small">
          {settings.last_sync ? `Last checked ${formatDateTime(settings.last_sync)}.` : "Not checked yet."}
          {settings.next_sync ? ` Next check ${formatDateTime(settings.next_sync)}.` : ""}
        </span>
      </div>
      {!ready && <p className="muted small">Connect Radarr and pick a folder for trailers first.</p>}
      {sync.isPending && (
        <div aria-live="polite" className="stack-sm">
          <ProgressBar value={progress?.progress ?? 0} label="Downloading trailers" />
          <p className="muted small">{progress?.status || "Asking Radarr what's coming…"}</p>
        </div>
      )}
      {sync.data && !sync.isPending && (
        <div aria-live="polite" className="stack-sm">
          <ResultNotice result={sync.data.movies} title={sync.data.shows ? "Movies" : undefined} />
          {sync.data.shows && <ResultNotice result={sync.data.shows} title="TV shows" />}
        </div>
      )}
      {sync.isError && <ErrorNotice error={sync.error} />}
    </div>
  );
}

interface UpcomingAnswer<T> {
  failed_servers?: string[];
  /** False when no server answered: an empty list then means "don't know". */
  read_any?: boolean;
  movies?: T[];
  shows?: T[];
}

function Unreachable({ app, names }: { app: string; names: string[] }) {
  return (
    <Notice tone="error" title={`Prerolls Max can't reach ${names.length ? listWords(names) : app} right now`}>
      <p>So it can't show what's coming. Check that {app} is running and that its address hasn't changed.</p>
      <p className="small">Trailers you already have keep playing.</p>
    </Notice>
  );
}

function showLine(s: UpcomingShow): string {
  const start = s.release_date ? formatDay(s.release_date, true) : "";
  const when = s.available_now ? "Out now" : start ? `Starts ${start}` : "No date yet";
  const what = s.release_type === "new_show" ? "New show" : s.season_number ? `Season ${s.season_number}` : "";
  return [what, when, s.downloaded ? "Trailer downloaded" : "No trailer yet"].filter(Boolean).join(" · ");
}

export function UpcomingList({ settings }: { settings: TrailerSettings }) {
  const movies = useQuery({
    queryKey: ["upcoming", "movies"],
    enabled: settings.radarr_connected,
    queryFn: () => api.get<UpcomingAnswer<UpcomingMovie>>("/nexup/radarr/upcoming", undefined, { timeoutMs: 60_000 }),
  });
  const shows = useQuery({
    queryKey: ["upcoming", "shows"],
    enabled: settings.sonarr_connected,
    queryFn: () => api.get<UpcomingAnswer<UpcomingShow>>("/nexup/sonarr/upcoming", undefined, { timeoutMs: 60_000 }),
  });
  if (!settings.radarr_connected && !settings.sonarr_connected) {
    return <p className="muted">Connect Radarr to see the movies coming soon.</p>;
  }
  const movieList = movies.data?.movies ?? [];
  const showList = shows.data?.shows ?? [];
  const movieFailed = movies.data?.failed_servers ?? [];
  const showFailed = shows.data?.failed_servers ?? [];
  return (
    <div className="stack">
      {movies.isLoading && <Loading label="Asking Radarr…" />}
      {movies.isError && <ErrorNotice error={movies.error} onRetry={() => movies.refetch()} />}
      {movies.data &&
        (movies.data.read_any === false ? (
          <Unreachable app="Radarr" names={movieFailed} />
        ) : (
          <>
            {movieFailed.length ? <Notice tone="warning">{missingServers(movieFailed, "movies")}</Notice> : null}
            {!movieList.length ? (
              <EmptyState title="Nothing coming soon">Radarr has no movies coming out in the next {settings.days_ahead} days.</EmptyState>
            ) : (
              <ul className="list">
                {movieList.map((m) => (
                  <li key={m.radarr_id} className="list-row">
                    {m.downloaded ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <Circle size={20} className="muted" aria-hidden="true" />}
                    <div className="grow">
                      <strong>
                        {m.title}
                        {m.year ? ` (${m.year})` : ""}
                      </strong>
                      <div className="muted small">
                        {m.available_now ? "Out now" : m.release_date ? `Out ${formatDay(m.release_date, true)}` : "No date yet"}
                        {m.downloaded ? " · Trailer downloaded" : " · No trailer yet"}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ))}
      {settings.sonarr_connected && (shows.data || shows.isError) && (
        <>
          <h3>TV shows</h3>
          {shows.isError && <ErrorNotice error={shows.error} onRetry={() => shows.refetch()} />}
          {shows.data?.read_any === false ? (
            <Unreachable app="Sonarr" names={showFailed} />
          ) : (
            <>
              {showFailed.length ? <Notice tone="warning">{missingServers(showFailed, "shows")}</Notice> : null}
              {shows.data && !showList.length && <p className="muted">No new shows or seasons start in the next {settings.days_ahead} days.</p>}
              {showList.length > 0 && (
                <ul className="list">
                  {showList.map((s, i) => (
                    <li key={`${s.sonarr_id ?? s.title}-${s.season_number ?? 0}-${i}`} className="list-row">
                      {s.downloaded ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <Circle size={20} className="muted" aria-hidden="true" />}
                      <div className="grow">
                        <strong>{s.title}</strong>
                        <div className="muted small">{showLine(s)}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

export function DownloadedList() {
  const trailers = useQuery({
    queryKey: ["downloaded-trailers"],
    queryFn: async () => (await api.get<{ trailers: DownloadedTrailer[] }>("/nexup/trailers")).trailers,
  });
  if (trailers.isLoading) return <Loading />;
  if (trailers.isError) return <ErrorNotice error={trailers.error} onRetry={() => trailers.refetch()} />;
  const list = trailers.data ?? [];
  if (!list.length) return <p className="muted">No trailers downloaded yet. Press Get trailers now.</p>;
  return (
    <>
      <p className="muted small">{plural(list.length, "trailer")} ready to play.</p>
      <ul className="list">
        {list.map((t) => (
          <li key={t.id} className="list-row">
            <div className="grow">
              <strong>
                {t.title}
                {t.year ? ` (${t.year})` : ""}
              </strong>
              <div className="muted small">
                {t.release_date ? `Out ${formatDay(t.release_date, true)}` : ""}
                {typeof t.days_until === "number" && t.days_until > 0 ? `, in ${plural(t.days_until, "day")}` : ""}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
