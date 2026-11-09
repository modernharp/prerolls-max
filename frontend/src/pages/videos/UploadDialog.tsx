// Add intro videos: upload files from this computer, or download one from a
// web link. Files are checked for type and size before sending, then sent
// one at a time with a progress bar each (see useUploadList and UploadRow).
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { AlertCircle, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { keys, useCategories } from "../../lib/queries";
import { cleanName } from "../../lib/validate";
import { plural } from "../../lib/format";
import { describeError } from "../../lib/errors";
import { fileKey } from "../../lib/uploadQueue";
import type { Category } from "../../lib/types";
import { Modal } from "../../components/Dialog";
import { Select } from "../../components/Select";
import { TextField } from "../../components/Field";
import { Button } from "../../components/Button";
import { Notice } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { UploadRow } from "./UploadRow";
import { LinkImport } from "./LinkImport";
import { useUploadList } from "./useUploadList";

const NEW = "__new";
const NO_COLLECTION = "__none";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialFiles?: File[];
  defaultCollection?: string;
  onUploaded?: (count: number) => void;
}

export function UploadDialog({ open, onOpenChange, initialFiles = [], defaultCollection = "", onUploaded }: Props) {
  const categories = useCategories();
  const queryClient = useQueryClient();
  const toast = useToast();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const list = useUploadList();
  const [tab, setTab] = useState<"files" | "link">("files");
  const [collection, setCollection] = useState(defaultCollection || NO_COLLECTION);
  const [newName, setNewName] = useState("");
  const [errors, setErrors] = useState<{ files?: string; newName?: string }>({});
  const [busy, setBusy] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setTab("files");
    setCollection(defaultCollection || NO_COLLECTION);
    list.add(initialFiles, true);
  }, [open]);

  const close = (next: boolean) => {
    if (busy || linkBusy) return;
    if (!next) list.skipWaitingDuplicates();
    onOpenChange(next);
  };

  /** The collection id to add to ("" for none), making a new one if asked. */
  const ensureCollection = useCallback(async (): Promise<string | null> => {
    if (collection !== NEW) return collection === NO_COLLECTION ? "" : collection;
    const check = cleanName(newName, { what: "collection name" });
    if (!check.ok) {
      setErrors((e) => ({ ...e, newName: check.message }));
      return null;
    }
    try {
      const created = await api.post<Category>("/categories", { name: check.value, description: "" });
      await queryClient.invalidateQueries({ queryKey: keys.categories });
      setCollection(String(created.id));
      setNewName("");
      return String(created.id);
    } catch (error) {
      const taken = (error as { status?: number }).status === 409;
      setErrors((e) => ({ ...e, newName: taken ? `There's already a collection called "${check.value}". Pick it from the list instead.` : describeError(error).message }));
      return null;
    }
  }, [collection, newName, queryClient]);

  async function start() {
    if (!list.sendable) {
      setErrors({ files: "Add at least one video." });
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      const categoryId = await ensureCollection();
      if (categoryId === null) return;
      const added = await list.send(categoryId);
      await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      if (added) {
        toast({ tone: "success", title: `${plural(added, "video")} added` });
        onUploaded?.(added);
      }
    } finally {
      setBusy(false);
    }
  }

  const choose = async (file: File, action: "add" | "skip") => {
    if (await list.choose(file, action)) {
      await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      onUploaded?.(1);
    }
  };

  const options = [
    { value: NO_COLLECTION, label: "No collection" },
    ...(categories.data ?? []).map((c) => ({ value: String(c.id), label: c.name })),
    { value: NEW, label: "+ New collection…" },
  ];
  const done = list.settled && !list.sendable;

  return (
    <Modal open={open} onOpenChange={close} title="Add intro videos" wide>
      <div className="stack">
        <Select label="Add them to" value={collection} onChange={setCollection} options={options} help="Schedules pick videos from collections." />
        {collection === NEW && (
          <TextField label="New collection name" placeholder="For example: Halloween" value={newName} onChange={(e) => setNewName(e.target.value)} error={errors.newName} />
        )}
        <Tabs.Root value={tab} onValueChange={(v) => setTab(v as "files" | "link")}>
          <Tabs.List className="tabs-list tabs-compact" aria-label="Where the videos come from">
            <Tabs.Trigger value="files" className="tab" disabled={linkBusy}>
              From this computer
            </Tabs.Trigger>
            <Tabs.Trigger value="link" className="tab" disabled={busy}>
              From a web link
            </Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="files" className="stack tab-panel">
            <div
              className={`dropzone ${errors.files ? "invalid" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                list.add(Array.from(e.dataTransfer.files));
                setErrors((x) => ({ ...x, files: undefined }));
              }}
            >
              <Upload size={32} aria-hidden="true" />
              <p>Drag video files here, or</p>
              <Button onClick={() => inputRef.current?.click()} aria-describedby={errors.files ? `${inputId}-err` : undefined}>
                Choose files
              </Button>
              <input
                ref={inputRef}
                id={inputId}
                type="file"
                accept="video/*,.mkv,.ts,.m4v"
                multiple
                hidden
                onChange={(e) => {
                  list.add(Array.from(e.target.files ?? []));
                  setErrors((x) => ({ ...x, files: undefined }));
                  e.target.value = "";
                }}
              />
              <p className="muted small">MP4 works on every media server. Up to 500 MB each.</p>
            </div>
            {errors.files && (
              <p id={`${inputId}-err`} className="field-error">
                <AlertCircle size={16} aria-hidden="true" /> {errors.files}
              </p>
            )}
            {list.note && <Notice tone="info">{list.note}</Notice>}
            {list.files.length > 0 && (
              <ul className="upload-list" aria-live="polite" aria-label="Files to add">
                {list.files.map((file) => (
                  <UploadRow
                    key={fileKey(file)}
                    name={file.name}
                    size={file.size}
                    state={list.states[fileKey(file)]}
                    onRemove={busy ? undefined : () => list.remove(file)}
                    onChoose={(action) => void choose(file, action)}
                  />
                ))}
              </ul>
            )}
          </Tabs.Content>
          <Tabs.Content value="link" className="tab-panel">
            <LinkImport ensureCollection={ensureCollection} onBusy={setLinkBusy} onAdded={() => onUploaded?.(1)} />
          </Tabs.Content>
        </Tabs.Root>
      </div>
      <div className="dialog-footer">
        {tab === "files" && list.files.length > 0 && !busy && (
          <Button variant="ghost" onClick={list.clear} className="footer-start">
            Clear list
          </Button>
        )}
        <Button onClick={() => close(false)} disabled={busy || linkBusy}>
          {done || tab === "link" ? "Done" : "Cancel"}
        </Button>
        {tab === "files" && !done && (
          <Button variant="primary" onClick={start} loading={busy}>
            {busy ? "Uploading…" : list.sendable ? `Upload ${plural(list.sendable, "video")}` : "Upload"}
          </Button>
        )}
      </div>
    </Modal>
  );
}
