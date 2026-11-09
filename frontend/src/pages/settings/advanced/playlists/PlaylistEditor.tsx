// Build or change a playlist: a name, then steps in order.
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { useCategories, usePrerolls } from "../../../../lib/queries";
import { cleanName } from "../../../../lib/validate";
import { videoName } from "../../../../lib/format";
import { cloneSequenceWithIds, sequenceHasUnsavedChanges, validateBlock, type Block } from "../../../../lib/playlist";
import { usePrefs } from "../../../../lib/prefs";
import { PageHeader } from "../../../../components/HelpPanel";
import { TextArea, TextField } from "../../../../components/Field";
import { Select } from "../../../../components/Select";
import { Button, ButtonLink } from "../../../../components/Button";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../../../components/Notice";
import { useToast } from "../../../../components/Toast";
import { StepCard, blankStep } from "./StepCard";
import { PlaylistPreview } from "./PlaylistPreview";
import { exportPlaylist, PLAYLISTS_KEY, savePlaylist, usePlaylists } from "./usePlaylists";
import { STEP_KINDS, type Lookup } from "./playlistText";
import { checkNameFree } from "../../../../lib/names";
import { isApiError } from "../../../../lib/errors";

export default function PlaylistEditor() {
  const { id = "new" } = useParams();
  const { advanced } = usePrefs();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const playlists = usePlaylists();
  const categories = useCategories();
  const prerolls = usePrerolls();
  const saved = id === "new" ? null : playlists.data?.find((p) => String(p.id) === id) ?? null;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [nameError, setNameError] = useState<string>();
  const [showErrors, setShowErrors] = useState(false);
  const [adding, setAdding] = useState("");

  useEffect(() => {
    if (saved) {
      setName(saved.name);
      setDescription(saved.description ?? "");
      setBlocks(cloneSequenceWithIds(saved.blocks));
    }
  }, [saved]);

  const lookup: Lookup = useMemo(
    () => ({
      collection: (cid) => categories.data?.find((c) => c.id === cid)?.name,
      video: (vid) => {
        const p = prerolls.data?.find((v) => v.id === vid);
        return p ? videoName(p) : undefined;
      },
    }),
    [categories.data, prerolls.data],
  );
  const stepErrors = blocks.map((b) => validateBlock(b, categories.data ?? [], prerolls.data ?? []));
  const dirty = sequenceHasUnsavedChanges(blocks, name, description, saved);

  const save = useMutation({
    mutationFn: (clean: string) => savePlaylist({ id: saved?.id, name: clean, description, blocks }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: PLAYLISTS_KEY });
      toast({ tone: "success", title: saved ? `Saved "${result.name}"` : `Made "${result.name}"` });
      if (!saved) navigate(`/settings/advanced/playlists/${result.id}`, { replace: true });
    },
    onError: (error) => {
      if (isApiError(error) && error.fields.name) setNameError(error.fields.name);
    },
  });

  const submit = () => {
    setShowErrors(true);
    const check = cleanName(name, { what: "playlist name" });
    const taken = check.ok ? checkNameFree("playlist", playlists.data, check.value, saved?.id, saved?.name) : undefined;
    setNameError(check.ok ? taken : check.message);
    if (!check.ok || taken || !blocks.length || stepErrors.some((e) => e.length)) return;
    save.mutate(check.value);
  };

  const update = (i: number, block: Block) => setBlocks((list) => list.map((b, j) => (j === i ? { ...block, id: b.id } : b)));
  const move = (i: number, delta: number) =>
    setBlocks((list) => {
      const next = [...list];
      const [item] = next.splice(i, 1);
      if (item) next.splice(i + delta, 0, item);
      return next;
    });
  const add = (type: string) => {
    setBlocks((list) => [...list, ...cloneSequenceWithIds([blankStep(type)])]);
    setAdding("");
  };

  if (!advanced) {
    return <EmptyState title="Playlists are an advanced option">Turn on advanced options in Settings to use them.</EmptyState>;
  }
  if (id !== "new" && playlists.isLoading) return <Loading />;
  if (id !== "new" && !saved && playlists.isSuccess) {
    return <ErrorNotice error={{}} title="That playlist doesn't exist anymore. It may have been deleted." />;
  }

  return (
    <>
      <ButtonLink to="/settings/advanced/playlists" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        Playlists
      </ButtonLink>
      <PageHeader
        title={saved ? `Edit "${saved.name}"` : "New playlist"}
        description="The steps play in order before the movie, like a cinema pre-show."
        helpSlug="playlists"
      />
      <div className="stack">
        <section className="card stack">
          <TextField label="Name" placeholder="For example: Friday night pre-show" value={name} onChange={(e) => setName(e.target.value)} error={nameError} />
          <TextArea label="Notes" optional value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </section>

        <section className="stack" aria-labelledby="steps-title">
          <h2 id="steps-title">Steps</h2>
          {!blocks.length ? (
            <EmptyState title="No steps yet">Add the first thing that should play, like a welcome video.</EmptyState>
          ) : (
            <ol className="step-list">
              {blocks.map((block, i) => (
                <StepCard
                  key={block.id ?? i}
                  block={block}
                  index={i}
                  total={blocks.length}
                  errors={showErrors ? stepErrors[i] ?? [] : []}
                  lookup={lookup}
                  onChange={(b) => update(i, b)}
                  onMove={(delta) => move(i, delta)}
                  onDuplicate={() => setBlocks((list) => [...list.slice(0, i + 1), ...cloneSequenceWithIds([block]), ...list.slice(i + 1)])}
                  onRemove={() => setBlocks((list) => list.filter((_, j) => j !== i))}
                />
              ))}
            </ol>
          )}
          <div className="toolbar">
            <div className="toolbar-select grow">
              <Select
                label={<span className="visually-hidden">Add a step</span>}
                value={adding}
                onChange={add}
                placeholder="Add a step…"
                options={STEP_KINDS.map((k) => ({ value: k.value, label: k.label }))}
              />
            </div>
          </div>
          {showErrors && !blocks.length && <p className="field-error">Add at least one step.</p>}
        </section>

        {save.isError && !(isApiError(save.error) && save.error.fields.name) && <ErrorNotice error={save.error} />}
        {showErrors && stepErrors.some((e) => e.length) && <Notice tone="error">Some steps need fixing. They're marked in red.</Notice>}
        <div className="form-actions">
          <Button variant="primary" onClick={submit} loading={save.isPending}>
            {saved ? "Save changes" : "Save playlist"}
          </Button>
          <Button
            icon={<Download size={18} aria-hidden="true" />}
            disabled={!blocks.length}
            onClick={() =>
              exportPlaylist({ id: dirty ? undefined : saved?.id, name: name || "Playlist", description, blocks }).catch((e: unknown) =>
                toast({ tone: "error", title: e instanceof Error ? e.message : "The file couldn't be made." }),
              )
            }
          >
            Export
          </Button>
          {dirty && saved && <span className="muted small">You have changes that aren't saved.</span>}
        </div>

        <PlaylistPreview blocks={blocks} lookup={lookup} />
      </div>
    </>
  );
}
