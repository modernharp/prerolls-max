// Trailers for movies already in the library (NeXroll's "Library Trailers"):
// trailer files that sit next to the movies, plus downloads from YouTube.
// They play from a "Trailers for movies you have" playlist step.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { api } from "../../../../lib/api";
import { plural } from "../../../../lib/format";
import { cleanFolderPath } from "../../../../lib/validate";
import { SwitchRow } from "../../../../components/Controls";
import { TextField } from "../../../../components/Field";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Loading } from "../../../../components/Notice";
import { useToast } from "../../../../components/Toast";
import { ResultNotice, type ActionResult } from "./ResultNotice";

interface LibraryConfig {
  enabled: boolean;
  use_local: boolean;
  download: boolean;
  path_mappings: { radarr: string; local: string }[];
}

interface SyncState {
  running: boolean;
  status?: string;
  stage?: string | null;
  error?: string | null;
  result?: { local_found?: number; downloaded?: number; failed?: number; removed?: number; candidates?: number } | null;
}

interface LibraryTrailer {
  id: number;
  title: string;
  year?: number | null;
  source: "local" | "download" | string;
  status: string;
  error_message?: string | null;
}

const KEY = ["library-trailers"] as const;

/** The finished sync's counts as one sentence. */
export function libraryResult(state: SyncState | undefined): ActionResult | null {
  if (!state || state.running) return null;
  if (state.error) return { success: false, message: state.error };
  const r = state.result;
  if (!r) return null;
  const parts: string[] = [];
  if (r.local_found) parts.push(`Found ${plural(r.local_found, "trailer file")} next to your movies.`);
  if (r.downloaded) parts.push(`Downloaded ${plural(r.downloaded, "trailer")}.`);
  if (r.removed) parts.push(`Removed ${plural(r.removed, "trailer")} for movies that left your library.`);
  if (r.failed) parts.push(`${plural(r.failed, "trailer")} couldn't be downloaded. The list below says why.`);
  if (!parts.length) parts.push(r.candidates ? "Nothing new this time." : "Radarr has no movies in its library yet.");
  return { success: !r.failed || Boolean(r.local_found || r.downloaded), trouble: Boolean(r.failed), message: parts.join(" ") };
}

function useLibrarySettings() {
  return useQuery({
    queryKey: [...KEY, "settings"],
    queryFn: () => api.get<{ config: LibraryConfig; radarr_connected: boolean; storage_path: string | null; sync: SyncState }>("/nexup/library/settings"),
  });
}

function TrailerRows() {
  const list = useQuery({ queryKey: [...KEY, "list"], queryFn: () => api.get<{ trailers: LibraryTrailer[] }>("/nexup/library/trailers") });
  if (list.isLoading) return <Loading />;
  if (list.isError) return <ErrorNotice error={list.error} onRetry={() => list.refetch()} />;
  const rows = list.data?.trailers ?? [];
  if (!rows.length) return <p className="muted">None yet. Press Find trailers now.</p>;
  const ready = rows.filter((t) => t.status === "available").length;
  return (
    <>
      <p className="muted small">{plural(ready, "trailer")} ready to play.</p>
      <ul className="list">
        {rows.map((t) => (
          <li key={t.id} className="list-row">
            {t.status === "available" ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <XCircle size={20} className="status-bad" aria-hidden="true" />}
            <div className="grow">
              <strong>
                {t.title}
                {t.year ? ` (${t.year})` : ""}
              </strong>
              <div className="muted small">
                {t.status === "available"
                  ? t.source === "local"
                    ? "Trailer file next to the movie"
                    : "Downloaded"
                  : t.error_message || "Couldn't be downloaded"}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

export function LibraryTrailers() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const settings = useLibrarySettings();
  const [radarrPath, setRadarrPath] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [pathError, setPathError] = useState<string>();
  const [watching, setWatching] = useState(false);
  const mapping = settings.data?.config.path_mappings?.[0];
  useEffect(() => {
    setRadarrPath(mapping?.radarr ?? "");
    setLocalPath(mapping?.local ?? "");
  }, [mapping?.radarr, mapping?.local]);

  const save = useMutation({
    mutationFn: (changes: Partial<LibraryConfig>) => api.put("/nexup/library/settings", changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
  const status = useQuery({
    queryKey: [...KEY, "status"],
    queryFn: () => api.get<SyncState>("/nexup/library/sync/status"),
    enabled: watching,
    refetchInterval: (q) => (q.state.data?.running === false ? false : 1500),
  });
  useEffect(() => {
    if (watching && status.data && !status.data.running) {
      setWatching(false);
      void queryClient.invalidateQueries({ queryKey: KEY });
    }
  }, [watching, status.data, queryClient]);
  const start = useMutation({
    mutationFn: () => api.post("/nexup/library/sync", {}),
    onSuccess: () => {
      void queryClient.removeQueries({ queryKey: [...KEY, "status"] });
      setWatching(true);
    },
  });

  if (settings.isLoading) return <Loading />;
  if (settings.isError || !settings.data) return <ErrorNotice error={settings.error} onRetry={() => settings.refetch()} />;
  const { config, radarr_connected, storage_path } = settings.data;
  const running = watching || start.isPending;
  const result = !running ? libraryResult(status.data ?? settings.data.sync) : null;

  const saveMapping = () => {
    if (!radarrPath.trim() && !localPath.trim()) {
      setPathError(undefined);
      save.mutate({ path_mappings: [] }, { onSuccess: () => toast({ tone: "success", title: "Folders saved" }) });
      return;
    }
    const a = cleanFolderPath(radarrPath, { what: "Radarr's folder" });
    const b = cleanFolderPath(localPath, { what: "folder" });
    if (!a.ok || !b.ok) {
      setPathError(!a.ok ? a.message : !b.ok ? b.message : undefined);
      return;
    }
    setPathError(undefined);
    save.mutate({ path_mappings: [{ radarr: a.value, local: b.value }] }, { onSuccess: () => toast({ tone: "success", title: "Folders saved" }) });
  };

  return (
    <div className="stack">
      <p className="muted">
        Trailers for movies you already have, to play before something else in your library. Prerolls Max uses trailer files
        that sit next to your movies (like &ldquo;Sintel (2010)-trailer.mp4&rdquo;) and can download the rest from YouTube.
        To play them, add a &ldquo;Trailers for movies you have&rdquo; step to a playlist.
      </p>
      {!radarr_connected && <p className="muted small">Connect Radarr above first.</p>}
      <SwitchRow
        label="Find trailers for movies you have"
        checked={config.enabled}
        disabled={save.isPending || !radarr_connected}
        onChange={(enabled) => save.mutate({ enabled })}
      />
      {config.enabled && (
        <>
          <SwitchRow
            label="Use trailer files next to your movies"
            description="Files ending in -trailer, or in a Trailers folder inside the movie's folder."
            checked={config.use_local}
            disabled={save.isPending}
            onChange={(use_local) => save.mutate({ use_local })}
          />
          <SwitchRow
            label="Download the rest from YouTube"
            description="Uses the trailer Radarr lists for each movie."
            checked={config.download}
            disabled={save.isPending}
            onChange={(download) => save.mutate({ download })}
          />
          <div className="form-grid">
            <TextField
              label="Radarr's movie folder"
              optional
              placeholder="/movies"
              help="Only if Radarr sees your movies under a different path, for example in Docker."
              value={radarrPath}
              error={pathError}
              onChange={(e) => setRadarrPath(e.target.value)}
            />
            <TextField
              label="The same folder for Prerolls Max"
              optional
              placeholder="/data/movies"
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
            />
          </div>
          <div>
            <Button size="sm" loading={save.isPending} onClick={saveMapping}>
              Save folders
            </Button>
          </div>
          {save.isError && <ErrorNotice error={save.error} />}
          <div className="row">
            <Button
              variant="primary"
              icon={<RefreshCw size={18} aria-hidden="true" />}
              loading={running}
              disabled={!radarr_connected || !storage_path}
              onClick={() => start.mutate()}
            >
              Find trailers now
            </Button>
            {!storage_path && <span className="muted small">Pick a folder for trailers under Trailer settings first.</span>}
          </div>
          {running && (
            <p className="muted small" aria-live="polite">
              {status.data?.status || "Reading your movies from Radarr…"}
            </p>
          )}
          {start.isError && <ErrorNotice error={start.error} />}
          {result && <ResultNotice result={result} />}
          <TrailerRows />
        </>
      )}
    </div>
  );
}
