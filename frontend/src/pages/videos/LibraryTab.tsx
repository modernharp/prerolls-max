import { useMemo, useState, type DragEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Film, LayoutGrid, List, Search, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { keys, useCategories, usePrerolls } from "../../lib/queries";
import { videoName } from "../../lib/format";
import { describeError } from "../../lib/errors";
import type { Preroll } from "../../lib/types";
import { Button, ButtonLink } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { EmptyState, ErrorNotice, Loading } from "../../components/Notice";
import { Select } from "../../components/Select";
import { useToast } from "../../components/Toast";
import { loudnessWords, useLoudness } from "../../lib/media";
import { PreviewDialog, VideoCard } from "./VideoCard";
import { EditVideoDialog } from "./EditVideoDialog";
import { UploadDialog } from "./UploadDialog";
import { useMediaJob } from "./media/useMediaJob";
import { LoudnessSummary } from "./media/LoudnessSummary";
import { SelectionBar } from "./media/SelectionBar";
import { NormalizeDialog } from "./media/NormalizeDialog";
import { VersionsDialog } from "./media/VersionsDialog";
import { CombineDialog } from "./media/CombineDialog";

type Tool = { kind: "normalize" | "versions" | "combine"; ids: number[] } | null;

const ALL = "all";
const NONE = "none";

interface DeleteResult {
  file_trashed?: boolean;
  trash_entry_id?: string | number | null;
}

export function LibraryTab() {
  const prerolls = usePrerolls();
  const categories = useCategories();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [collection, setCollection] = useState(ALL);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [preview, setPreview] = useState<Preroll | null>(null);
  const [editing, setEditing] = useState<Preroll | null>(null);
  const [deleting, setDeleting] = useState<Preroll | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [tool, setTool] = useState<Tool>(null);
  const loudness = useLoudness();
  const check = useMediaJob<{ checked: number }>("/api/media/loudness/check");

  // Versions (louder/quieter, TV-friendly) show under their original.
  const { originals, versionsOf } = useMemo(() => {
    const all = prerolls.data ?? [];
    const ids = new Set(all.map((p) => p.id));
    const versionsOf = new Map<number, Preroll[]>();
    for (const p of all) {
      if (p.version_of && ids.has(p.version_of)) versionsOf.set(p.version_of, [...(versionsOf.get(p.version_of) ?? []), p]);
    }
    return { originals: all.filter((p) => !(p.version_of && ids.has(p.version_of))), versionsOf };
  }, [prerolls.data]);

  const switchedOff = useMemo(() => new Set((prerolls.data ?? []).filter((p) => p.enabled === false).map((p) => p.id)), [prerolls.data]);

  const loudnessFor = useMemo(() => {
    const data = loudness.data;
    if (!data) return undefined;
    const byId = new Map(data.items.map((i) => [i.preroll_id, i]));
    return (p: Preroll) => {
      const item = byId.get(p.id);
      return item && item.status !== "unchecked" ? loudnessWords(item, data.target_lufs) : undefined;
    };
  }, [loudness.data]);

  const toggleSelected = (id: number) => setSelected((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));

  const shown = useMemo(() => {
    const words = search.toLowerCase().split(/\s+/).filter(Boolean);
    return originals.filter((p) => {
      if (collection === NONE && p.categories.length) return false;
      if (collection !== ALL && collection !== NONE && !p.categories.some((c) => String(c.id) === collection)) return false;
      const text = `${videoName(p)} ${p.filename} ${p.tags ?? ""}`.toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [originals, search, collection]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.prerolls });

  const remove = async (p: Preroll) => {
    const res = await api.del<DeleteResult>(`/prerolls/${p.id}?delete_file=true`);
    await refresh();
    const entry = res?.trash_entry_id;
    toast({
      tone: "success",
      title: `Deleted "${videoName(p)}"`,
      description: entry ? "It's in Trash for 30 days." : "It's gone from your library. The file was left where it was.",
      action: entry
        ? {
            label: "Undo",
            onClick: async () => {
              try {
                await api.post(`/prerolls/trash/${entry}/restore`, {});
                await refresh();
                toast({ tone: "success", title: `Restored "${videoName(p)}"` });
              } catch (error) {
                toast({ tone: "error", title: "Couldn't restore it", description: describeError(error).message });
              }
            },
          }
        : undefined,
    });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) {
      setDropped(Array.from(e.dataTransfer.files));
      setUploadOpen(true);
    }
  };

  const options = [
    { value: ALL, label: "All collections" },
    { value: NONE, label: "Not in a collection" },
    ...(categories.data ?? []).map((c) => ({ value: String(c.id), label: c.name })),
  ];

  return (
    <div
      className={`dropzone-page ${dragging ? "dragging" : ""}`}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="toolbar">
        <div className="field grow search-field">
          <label htmlFor="video-search" className="visually-hidden">
            Search your videos
          </label>
          <Search size={18} className="search-icon" aria-hidden="true" />
          <input
            id="video-search"
            className="input search-input"
            type="search"
            placeholder="Search by name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="toolbar-select">
          <Select label={<span className="visually-hidden">Collection</span>} value={collection} onChange={setCollection} options={options} />
        </div>
        <div className="row" role="group" aria-label="Layout">
          <Button variant={view === "grid" ? "primary" : "secondary"} className="btn-icon" aria-label="Show as grid" aria-pressed={view === "grid"} onClick={() => setView("grid")}>
            <LayoutGrid size={18} aria-hidden="true" />
          </Button>
          <Button variant={view === "list" ? "primary" : "secondary"} className="btn-icon" aria-label="Show as list" aria-pressed={view === "list"} onClick={() => setView("list")}>
            <List size={18} aria-hidden="true" />
          </Button>
        </div>
        <Button variant="primary" icon={<Upload size={18} aria-hidden="true" />} onClick={() => setUploadOpen(true)}>
          Add videos
        </Button>
      </div>

      <LoudnessSummary data={loudness.data} skip={switchedOff} check={check} onEvenOut={(ids) => setTool({ kind: "normalize", ids })} />

      {prerolls.isLoading ? (
        <Loading label="Loading your videos…" />
      ) : prerolls.isError ? (
        <ErrorNotice error={prerolls.error} onRetry={() => prerolls.refetch()} />
      ) : !prerolls.data?.length ? (
        <EmptyState
          icon={<Film size={40} />}
          title="No intro videos yet"
          action={
            <div className="row">
              <Button variant="primary" icon={<Upload size={18} aria-hidden="true" />} onClick={() => setUploadOpen(true)}>
                Add videos
              </Button>
              <ButtonLink to="/videos/community">Get free ones from Community</ButtonLink>
            </div>
          }
        >
          Drag video files here, or pick them from your computer. MP4 works everywhere.
        </EmptyState>
      ) : !shown.length ? (
        <EmptyState title="Nothing matches" action={<Button onClick={() => { setSearch(""); setCollection(ALL); }}>Show all videos</Button>}>
          No videos match your search or the collection you picked.
        </EmptyState>
      ) : (
        <>
          <p className="muted small" aria-live="polite">
            Showing {shown.length} of {originals.length}. Tick videos to check or even out their loudness, make TV-friendly versions or combine them.
          </p>
          <ul className={view === "grid" ? "video-grid" : "video-list"}>
            {shown.map((p) => (
              <VideoCard
                key={p.id}
                preroll={p}
                versions={versionsOf.get(p.id)}
                loudness={loudnessFor}
                selected={selected.includes(p.id)}
                onSelect={() => toggleSelected(p.id)}
                onPreview={setPreview}
                onEdit={() => setEditing(p)}
                onDelete={setDeleting}
              />
            ))}
          </ul>
        </>
      )}

      <SelectionBar
        count={selected.length}
        checking={check.running}
        onCheck={() => check.start.mutate({ preroll_ids: selected })}
        onEvenOut={() => setTool({ kind: "normalize", ids: selected })}
        onVersions={() => setTool({ kind: "versions", ids: selected })}
        onCombine={() => setTool({ kind: "combine", ids: selected })}
        onClear={() => setSelected([])}
      />

      {dragging && (
        <div className="drop-hint" aria-hidden="true">
          <Upload size={40} />
          Drop videos to upload them
        </div>
      )}

      <PreviewDialog preroll={preview} onClose={() => setPreview(null)} />
      <NormalizeDialog ids={tool?.kind === "normalize" ? tool.ids : []} open={tool?.kind === "normalize"} onClose={() => setTool(null)} />
      <VersionsDialog ids={tool?.kind === "versions" ? tool.ids : []} open={tool?.kind === "versions"} onClose={() => setTool(null)} />
      <CombineDialog ids={tool?.kind === "combine" ? tool.ids : []} open={tool?.kind === "combine"} onClose={() => setTool(null)} />
      <EditVideoDialog preroll={editing} onClose={() => setEditing(null)} />
      <UploadDialog
        open={uploadOpen}
        initialFiles={dropped}
        defaultCollection={collection !== ALL && collection !== NONE ? collection : ""}
        onOpenChange={(o) => {
          setUploadOpen(o);
          if (!o) setDropped([]);
        }}
      />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={deleting ? `Delete "${videoName(deleting)}"?` : ""}
        body={<p>It stops playing before movies. You can restore it from Trash for 30 days.</p>}
        confirmLabel="Delete"
        danger
        onConfirm={() => (deleting ? remove(deleting) : undefined)}
      />
    </div>
  );
}
