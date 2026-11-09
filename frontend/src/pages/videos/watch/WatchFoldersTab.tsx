// Intro Videos, Add automatically: folders Prerolls Max watches for new
// intro videos, and what happened to the files it found.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FolderInput, Hourglass, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../../../lib/api";
import { describeError } from "../../../lib/errors";
import { keys } from "../../../lib/queries";
import { plural } from "../../../lib/format";
import { timeAgo } from "../../../lib/stats";
import { mediaKeys, useWatchFolders, type WatchCheckResult, type WatchFolder } from "../../../lib/media";
import { Button, IconButton } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/Dialog";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../../components/Notice";
import { FeatureBadges } from "../../../components/FeatureBadges";
import { useToast } from "../../../components/Toast";
import { WatchFolderDialog } from "./WatchFolderDialog";

const errorText = (e: WatchCheckResult["errors"][number]) => (typeof e === "string" ? e : e.message ?? e.name ?? "");

function FolderCard({ folder, onEdit, onDelete }: { folder: WatchFolder; onEdit: () => void; onDelete: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [result, setResult] = useState<WatchCheckResult | null>(null);
  const check = useMutation({
    mutationFn: () => api.post<WatchCheckResult>(`/api/watch-folders/${folder.id}/check`, {}),
    onSuccess: async (r) => {
      setResult(r);
      await queryClient.invalidateQueries({ queryKey: mediaKeys.watch });
      if (r.imported.length) await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      toast({
        tone: "success",
        title: r.imported.length ? `Added ${plural(r.imported.length, "video")}` : "Nothing new to add",
        description: r.imported.map((i) => i.name).join(", ") || (r.waiting.length ? `${plural(r.waiting.length, "file")} still arriving.` : undefined),
      });
    },
    onError: (error) => toast({ tone: "error", title: describeError(error).message, description: describeError(error).hint }),
  });
  const status = !folder.exists ? (
    <span className="badge badge-danger">Folder missing</span>
  ) : folder.enabled ? (
    <span className="badge badge-success">Watching</span>
  ) : (
    <span className="badge">Off</span>
  );
  const waiting = folder.waiting.length ? folder.waiting : result?.waiting ?? [];
  const errors = (result?.errors ?? []).map(errorText).filter(Boolean);
  return (
    <li className="card stack-sm watch-card">
      <div className="row-between">
        <div className="row grow">
          <FolderInput size={22} aria-hidden="true" />
          <code className="watch-path">{folder.path}</code>
          {status}
        </div>
        <div className="row">
          <Button size="sm" icon={<RefreshCw size={16} aria-hidden="true" />} loading={check.isPending} onClick={() => check.mutate()} disabled={!folder.enabled}>
            Check now
          </Button>
          <IconButton label={`Change ${folder.path}`} onClick={onEdit}>
            <Pencil size={18} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Stop watching ${folder.path}`} onClick={onDelete}>
            <Trash2 size={18} aria-hidden="true" />
          </IconButton>
        </div>
      </div>
      <p className="muted small">
        New videos go to {folder.collection_name ? `"${folder.collection_name}"` : "no collection"} and{" "}
        {folder.mode === "copy" ? "are copied into the library" : "are used where they are"}
        {folder.recursive ? ", including folders inside it" : ""}. {plural(folder.imported_count, "video")} added so far
        {folder.last_checked_at ? `, last checked ${timeAgo(folder.last_checked_at)}` : ""}.
        {folder.duplicate_count ? ` Skipped ${plural(folder.duplicate_count, "duplicate")}: the same video was already in your library.` : ""}
      </p>
      {folder.problem && (
        <p className="rule-problem">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{folder.problem}</span>
        </p>
      )}
      {errors.length > 0 && (
        <Notice tone="warning" title="Some files weren't added">
          <ul className="plain-list small">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Notice>
      )}
      {waiting.length > 0 && (
        <div className="waiting">
          <p className="small row">
            <Hourglass size={14} aria-hidden="true" /> <strong>Waiting</strong>
          </p>
          <ul className="plain-list small">
            {waiting.map((w) => (
              <li key={w.name}>
                {w.name} <span className="muted">· {w.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

export function WatchFoldersTab() {
  const folders = useWatchFolders();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<WatchFolder | "new" | null>(null);
  const [removing, setRemoving] = useState<WatchFolder | null>(null);
  const list = folders.data ?? [];

  const remove = async (f: WatchFolder) => {
    await api.del(`/api/watch-folders/${f.id}`);
    await queryClient.invalidateQueries({ queryKey: mediaKeys.watch });
    toast({ tone: "success", title: `Stopped watching ${f.path}`, description: "The folder and the videos already added are left as they are." });
  };

  return (
    <>
      <div className="row-between section-gap">
        <div className="grow">
          <p className="muted">
            Pick a folder and a collection. New intro videos you put in that folder are added on their own, like a download folder
            or a shared folder someone else fills. Prerolls Max checks every 30 seconds and waits until a file stops changing.
          </p>
          <FeatureBadges feature="watch_folders" />
        </div>
        <Button variant="primary" icon={<Plus size={18} aria-hidden="true" />} onClick={() => setEditing("new")}>
          Watch a folder
        </Button>
      </div>
      {folders.isLoading ? (
        <Loading />
      ) : folders.isError ? (
        <ErrorNotice error={folders.error} onRetry={() => folders.refetch()} />
      ) : !list.length ? (
        <EmptyState icon={<FolderInput size={40} />} title="No watch folders yet" action={<Button variant="primary" onClick={() => setEditing("new")}>Watch a folder</Button>}>
          Files that are still downloading (.part, .crdownload) and hidden files are never touched.
        </EmptyState>
      ) : (
        <ul className="list">
          {list.map((f) => (
            <FolderCard key={f.id} folder={f} onEdit={() => setEditing(f)} onDelete={() => setRemoving(f)} />
          ))}
        </ul>
      )}
      <WatchFolderDialog folder={editing} onClose={() => setEditing(null)} />
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? `Stop watching ${removing.path}?` : ""}
        body={<p>The folder, its files and the intro videos already added from it stay as they are.</p>}
        confirmLabel="Stop watching"
        danger
        onConfirm={() => (removing ? remove(removing) : undefined)}
      />
    </>
  );
}
