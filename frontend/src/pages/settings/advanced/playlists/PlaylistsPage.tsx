// Advanced > Playlists: the saved playlists, plus import and export.
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ListOrdered, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { api } from "../../../../lib/api";
import { useCategories, usePrerolls } from "../../../../lib/queries";
import { cleanName } from "../../../../lib/validate";
import { plural, videoName } from "../../../../lib/format";
import { withoutImportNotes, type SavedPlaylist } from "../../../../lib/playlist";
import { describeError } from "../../../../lib/errors";
import { Button, ButtonLink, IconButton } from "../../../../components/Button";
import { ConfirmDialog, Modal } from "../../../../components/Dialog";
import { TextField } from "../../../../components/Field";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../../../components/Notice";
import { useToast } from "../../../../components/Toast";
import { describeCondition, describeStep, type Lookup } from "./playlistText";
import { exportPlaylist, importPlaylistFile, PLAYLISTS_KEY, savePlaylist, usePlaylists, type ImportResult } from "./usePlaylists";
import { checkNameFree, nameKey, sharedNameIds } from "../../../../lib/names";
import { isApiError } from "../../../../lib/errors";
import { SharedNameHint } from "../../../../components/SharedNameHint";

function ImportDialog({ result, onClose, others }: { result: ImportResult; onClose: () => void; others: SavedPlaylist[] }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const suggested = result.suggested_name || result.pattern_name;
  const renamed = nameKey(suggested) !== nameKey(result.pattern_name);
  const [name, setName] = useState(suggested);
  const [error, setError] = useState<string>();
  const save = useMutation({
    mutationFn: (clean: string) => savePlaylist({ name: clean, description: result.pattern_description ?? "", blocks: withoutImportNotes(result.blocks) }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: PLAYLISTS_KEY });
      onClose();
      navigate(`/settings/advanced/playlists/${saved.id}`);
    },
    onError: (e) => {
      if (isApiError(e) && e.fields.name) setError(e.fields.name);
    },
  });
  const m = result.match_results;
  const missing = [...(m.missing_categories ?? []), ...(m.missing_prerolls ?? [])];
  const submit = () => {
    const check = cleanName(name, { what: "playlist name" });
    const taken = check.ok ? checkNameFree("playlist", others, check.value) : undefined;
    setError(check.ok ? taken : check.message);
    if (check.ok && !taken) save.mutate(check.value);
  };
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Import a playlist">
      <div className="stack">
        <p>
          {plural(m.total_blocks, "step")} in the file. {m.matched} matched your library
          {m.unmatched ? `, ${m.unmatched} didn't` : ""}.
        </p>
        {missing.length > 0 && (
          <Notice tone="warning" title="Some things aren't in your library">
            <p>{missing.slice(0, 8).join(", ")}{missing.length > 8 ? ", and more" : ""}.</p>
            <p>The steps that use them are left out or need a new pick. You can fix them after importing.</p>
          </Notice>
        )}
        {renamed && (
          <Notice tone="info">
            You already have a playlist called "{result.pattern_name.trim()}", so this one is saved as "{suggested}" unless you
            change the name below.
          </Notice>
        )}
        <TextField label="Save it as" value={name} onChange={(e) => setName(e.target.value)} error={error} />
        {save.isError && !error && <ErrorNotice error={save.error} />}
        <div className="dialog-footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} onClick={submit} disabled={!result.blocks.length}>
            Save playlist
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function PlaylistsPage() {
  const playlists = usePlaylists();
  const categories = useCategories();
  const prerolls = usePrerolls();
  const queryClient = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState<SavedPlaylist | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);
  const importer = useMutation({ mutationFn: importPlaylistFile, onSuccess: setImported });

  const lookup: Lookup = useMemo(
    () => ({
      collection: (id) => categories.data?.find((c) => c.id === id)?.name,
      video: (id) => {
        const p = prerolls.data?.find((v) => v.id === id);
        return p ? videoName(p) : undefined;
      },
    }),
    [categories.data, prerolls.data],
  );

  const pickFile = (file?: File) => {
    if (!file) return;
    if (!/\.(nexseq|json)$/i.test(file.name)) {
      toast({ tone: "error", title: "That isn't a playlist file.", description: "Pick a file that ends in .nexseq." });
      return;
    }
    importer.mutate(file);
  };

  const list = playlists.data ?? [];
  const shared = sharedNameIds(list);
  return (
    <div className="stack">
      <p className="muted">
        A playlist plays several things in order before a movie: a welcome video, a couple of trailers, then your feature
        intro. Steps can depend on the movie, like a horror intro only before horror films. To use one, pick it when you
        make a schedule, or as your default intros.
      </p>
      <div className="form-actions">
        <ButtonLink to="/settings/advanced/playlists/new" variant="primary" icon={<Plus size={18} aria-hidden="true" />}>
          New playlist
        </ButtonLink>
        <Button icon={<Upload size={18} aria-hidden="true" />} loading={importer.isPending} onClick={() => fileRef.current?.click()}>
          Import a .nexseq file
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".nexseq,.json,application/json"
          className="visually-hidden"
          aria-label="Playlist file to import"
          tabIndex={-1}
          onChange={(e) => {
            pickFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {importer.isError && <ErrorNotice error={importer.error} />}

      {playlists.isLoading ? (
        <Loading />
      ) : playlists.isError ? (
        <ErrorNotice error={playlists.error} onRetry={() => playlists.refetch()} />
      ) : !list.length ? (
        <EmptyState icon={<ListOrdered size={40} />} title="No playlists yet">
          Make one, or import a .nexseq file someone shared.
        </EmptyState>
      ) : (
        <ul className="list">
          {list.map((p) => (
            <li key={p.id} className="list-row">
              <div className="grow">
                <strong>{p.name}</strong>
                {shared.has(p.id) && <SharedNameHint kind="playlist" />}
                <ol className="muted small playlist-summary">
                  {p.blocks.slice(0, 4).map((b, i) => (
                    <li key={i}>
                      {describeStep(b, lookup)}
                      {describeCondition(b) ? ` (${describeCondition(b)?.toLowerCase()})` : ""}
                    </li>
                  ))}
                  {p.blocks.length > 4 && <li>and {plural(p.blocks.length - 4, "more step")}</li>}
                </ol>
              </div>
              <IconButton
                label={`Export ${p.name}`}
                onClick={() => exportPlaylist(p).catch((e: unknown) => toast({ tone: "error", title: describeError(e).message }))}
              >
                <Download size={18} aria-hidden="true" />
              </IconButton>
              <ButtonLink to={`/settings/advanced/playlists/${p.id}`} variant="ghost" className="btn-icon" aria-label={`Edit ${p.name}`}>
                <Pencil size={18} aria-hidden="true" />
              </ButtonLink>
              <IconButton label={`Delete ${p.name}`} onClick={() => setDeleting(p)}>
                <Trash2 size={18} aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
      {imported && <ImportDialog key={imported.pattern_name} result={imported} others={list} onClose={() => setImported(null)} />}
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={deleting ? `Delete "${deleting.name}"?` : ""}
        body={<p>Schedules that use it keep their own copy and carry on playing. This can't be undone.</p>}
        confirmLabel="Delete playlist"
        danger
        onConfirm={async () => {
          if (!deleting) return;
          await api.del(`/sequences/${deleting.id}`);
          await queryClient.invalidateQueries({ queryKey: PLAYLISTS_KEY });
          toast({ tone: "success", title: `Deleted "${deleting.name}"` });
        }}
      />
    </div>
  );
}
