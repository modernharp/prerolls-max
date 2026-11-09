// Advanced > Storage: where intro videos live, how much space everything uses,
// and moving the intro folder.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { ApiError } from "../../../lib/errors";
import { cleanFolderPath } from "../../../lib/validate";
import { formatDateTime, formatSize, plural } from "../../../lib/format";
import { TextField } from "../../../components/Field";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/Dialog";
import { ErrorNotice, Loading, Notice } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

interface Folder {
  current_folder: string;
  default_folder: string;
  is_custom: boolean;
  file_count: number;
  total_size_mb: number;
}

interface Breakdown {
  locations: { key: string; label: string; bytes: number; path: string | null }[];
  total_bytes: number;
  checked_at: string;
}

interface Health {
  missing_files: number;
  files_on_disk: number;
  db_rows_total: number;
  storage_maybe_offline: boolean;
}

const LABELS: Record<string, string> = {
  prerolls: "Intro videos",
  nexup: "Movie trailers and video maker",
  thumbnails: "Thumbnails",
  database: "Settings and history",
};

/** Some of these endpoints answer 200 with {error}; treat that as an error. */
async function orError<T extends object>(call: Promise<T & { error?: string }>): Promise<T> {
  const result = await call;
  if (result && typeof result === "object" && "error" in result && result.error) {
    throw new ApiError({ kind: "invalid", message: String(result.error), hint: "Check the folder and try again." });
  }
  return result;
}

function Usage() {
  const breakdown = useQuery({ queryKey: ["storage-breakdown"], queryFn: () => api.get<Breakdown>("/system/storage/breakdown", undefined, { timeoutMs: 60_000 }) });
  const health = useQuery({ queryKey: ["storage-health"], queryFn: () => api.get<Health>("/system/health/storage") });
  if (breakdown.isLoading) return <Loading label="Adding up sizes…" />;
  if (breakdown.isError) return <ErrorNotice error={breakdown.error} onRetry={() => breakdown.refetch()} />;
  const data = breakdown.data;
  const total = data?.total_bytes || 1;
  return (
    <div className="stack">
      {health.data?.storage_maybe_offline && (
        <Notice tone="error" title="The intro folder looks offline">
          Prerolls Max can't see most of its videos. If they're on a network drive or USB disk, check it's connected.
        </Notice>
      )}
      {Boolean(health.data?.missing_files) && !health.data?.storage_maybe_offline && (
        <Notice tone="warning">{plural(health.data?.missing_files ?? 0, "video is", "videos are")} in the library but missing from the folder.</Notice>
      )}
      <ul className="plain-list">
        {data?.locations.map((l) => (
          <li key={l.key} className="stack-sm">
            <div className="row-between">
              <strong>{LABELS[l.key] ?? l.label}</strong>
              <span>{formatSize(l.bytes) || "Empty"}</span>
            </div>
            <div className="meter" aria-hidden="true">
              <span style={{ width: `${Math.max(1, Math.round((l.bytes / total) * 100))}%` }} />
            </div>
            <span className="muted small">{l.path ?? "Not set up"}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">
        {formatSize(data?.total_bytes) || "0 bytes"} in total. Counted {formatDateTime(data?.checked_at)}.
      </p>
    </div>
  );
}

export function StoragePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const folder = useQuery({ queryKey: ["preroll-folder"], queryFn: () => api.get<Folder>("/settings/preroll-folder") });
  const [path, setPath] = useState("");
  const [error, setError] = useState<string>();
  const [confirm, setConfirm] = useState<string | null>(null);
  const move = useMutation({
    mutationFn: (target: string) => orError(api.post<{ error?: string; message?: string }>("/settings/preroll-folder/move", { new_folder: target, move_files: true }, { timeoutMs: 10 * 60_000 })),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      setPath("");
      toast({ tone: "success", title: "Moved your intro videos" });
    },
  });

  const submit = () => {
    const check = cleanFolderPath(path, { what: "intro folder" });
    setError(check.ok ? undefined : check.message);
    if (check.ok) setConfirm(check.value);
  };

  return (
    <div className="stack">
      <section className="card stack" aria-labelledby="st-use">
        <h2 id="st-use">Space used</h2>
        <Usage />
      </section>
      <section className="card stack" aria-labelledby="st-folder">
        <h2 id="st-folder">Intro folder</h2>
        {folder.isLoading ? (
          <Loading />
        ) : folder.isError ? (
          <ErrorNotice error={folder.error} />
        ) : (
          <dl className="facts">
            <dt>Folder</dt>
            <dd>
              <code>{folder.data?.current_folder}</code>
            </dd>
            <dt>Holds</dt>
            <dd>
              {plural(folder.data?.file_count ?? 0, "file")}, {formatSize((folder.data?.total_size_mb ?? 0) * 1024 * 1024) || "0 bytes"}
            </dd>
          </dl>
        )}
        <TextField
          label="Move intro videos to another folder"
          help="Use the full path, as Prerolls Max sees it. Your videos move there and the library follows them."
          placeholder="/data/prerolls"
          value={path}
          error={error}
          onChange={(e) => setPath(e.target.value)}
        />
        {move.isError && <ErrorNotice error={move.error} />}
        <div>
          <Button onClick={submit} loading={move.isPending}>
            Move videos
          </Button>
        </div>
        <p className="muted small">After moving, update Folder mapping if your media server sees the folder under another path.</p>
      </section>
      <ConfirmDialog
        open={Boolean(confirm)}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Move your intro videos?"
        body={
          <p>
            Every video moves to <code>{confirm}</code>. This can take a while with a large library. Your media servers keep
            working once it's done.
          </p>
        }
        confirmLabel="Move them"
        onConfirm={() => (confirm ? move.mutateAsync(confirm) : undefined)}
      />
    </div>
  );
}
