// Download the picked community videos in one job, with progress.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { keys, useCategories } from "../../../lib/queries";
import { cleanName } from "../../../lib/validate";
import { plural } from "../../../lib/format";
import { Modal } from "../../../components/Dialog";
import { Select } from "../../../components/Select";
import { TextField } from "../../../components/Field";
import { Button } from "../../../components/Button";
import { ErrorNotice, Notice, ProgressBar } from "../../../components/Notice";
import { useAcceptTerms, useJob, type CommunityItem, type CommunitySource, type DownloadResult } from "./useCommunity";

const NEW = "__new";
const NONE = "__none";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: CommunityItem[];
  sources: CommunitySource[];
  onFinished: () => void;
}

function TermsFirst({ source }: { source: CommunitySource }) {
  const accept = useAcceptTerms(source.id);
  return (
    <Notice tone="info" title={`${source.name}: please read first`}>
      <p>{source.terms.summary}</p>
      <p>
        <a href={source.terms.url} target="_blank" rel="noreferrer noopener">
          Read the full policy
        </a>
      </p>
      {accept.isError && <ErrorNotice error={accept.error} />}
      <Button size="sm" variant="primary" loading={accept.isPending} onClick={() => accept.mutate()}>
        I agree
      </Button>
    </Notice>
  );
}

function Outcome({ result, titleOf }: { result: DownloadResult; titleOf: (id: string) => string }) {
  return (
    <>
      {result.added.length > 0 && (
        <Notice tone="success" title={`Added ${plural(result.added.length, "video")}`}>
          <p>
            {result.collection ? `They're in the ${result.collection.name} collection. ` : ""}
            <Link to="/videos">See them in Your videos</Link>
          </p>
        </Notice>
      )}
      {result.skipped.length > 0 && (
        <Notice tone="info" title={`${plural(result.skipped.length, "video was", "videos were")} already in your library`}>
          <ul>
            {result.skipped.map((s) => (
              <li key={s.item_id}>{s.title ?? titleOf(s.item_id)}</li>
            ))}
          </ul>
        </Notice>
      )}
    </>
  );
}

export function DownloadDialog({ open, onOpenChange, items: picked, sources, onFinished }: Props) {
  // Keep the list as it was when the dialog opened; the selection clears when the download finishes.
  const [items, setItems] = useState<CommunityItem[]>([]);
  const categories = useCategories();
  const queryClient = useQueryClient();
  const [collection, setCollection] = useState(NONE);
  const [newName, setNewName] = useState("");
  const [nameError, setNameError] = useState<string>();
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob<DownloadResult>(jobId);

  useEffect(() => {
    if (open) {
      setItems(picked);
      setJobId(null);
      setNameError(undefined);
    }
  }, [open]); // only when the dialog opens

  const needTerms = sources.filter((s) => s.terms.needs_acceptance && !s.terms.accepted && items.some((i) => i.source === s.id));

  const start = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = { item_ids: items.map((i) => i.id) };
      if (collection === NEW) body.new_collection_name = newName.trim();
      else if (collection !== NONE) body.collection_id = Number(collection);
      return api.post<{ job_id: string }>("/api/community/download", body);
    },
    onSuccess: (res) => setJobId(res.job_id),
  });

  const state = job.data?.state;
  useEffect(() => {
    if (state === "done" || state === "failed") {
      void queryClient.invalidateQueries({ queryKey: keys.prerolls });
      void queryClient.invalidateQueries({ queryKey: keys.categories });
      void queryClient.invalidateQueries({ queryKey: ["community", "items"] });
      if (state === "done") onFinished();
    }
  }, [state, queryClient, onFinished]);

  const submit = () => {
    if (collection === NEW) {
      const check = cleanName(newName, { what: "collection name" });
      if (!check.ok) {
        setNameError(check.message);
        return;
      }
    }
    setNameError(undefined);
    start.mutate();
  };

  const running = Boolean(jobId) && state !== "done" && state !== "failed";
  const titleOf = (id: string) => items.find((i) => i.id === id)?.title ?? "A video";
  const options = [
    { value: NONE, label: "No collection" },
    ...(categories.data ?? []).filter((c) => !c.is_system).map((c) => ({ value: String(c.id), label: c.name })),
    { value: NEW, label: "+ New collection…" },
  ];
  const fromBoth = new Set(items.map((i) => i.source)).size > 1;

  return (
    <Modal open={open} onOpenChange={(o) => !running && onOpenChange(o)} title={`Download ${plural(items.length, "video")}`}>
      {needTerms.length > 0 ? (
        <div className="stack">
          {needTerms.map((s) => (
            <TermsFirst key={s.id} source={s} />
          ))}
        </div>
      ) : jobId ? (
        <div className="stack" aria-live="polite">
          <ProgressBar value={job.data?.progress ?? 0} label="Download progress" />
          <p>
            {job.data?.message || "Starting…"} ({job.data?.done ?? 0} of {job.data?.total ?? items.length})
          </p>
          {state === "done" && job.data?.result && <Outcome result={job.data.result} titleOf={titleOf} />}
          {job.data?.errors.length ? (
            <Notice tone="warning" title={`${plural(job.data.errors.length, "video")} didn't download`}>
              <ul>
                {job.data.errors.map((e, i) => (
                  <li key={`${e.item_id ?? "job"}-${i}`}>
                    {e.item_id ? `${titleOf(e.item_id)}: ` : ""}
                    {e.message}
                  </li>
                ))}
              </ul>
            </Notice>
          ) : null}
          {state === "failed" && !job.data?.errors.length && <Notice tone="error" title="The download stopped">{job.data?.message}</Notice>}
          {job.isError && <ErrorNotice error={job.error} />}
          <div className="dialog-footer">
            <Button variant="primary" disabled={running} onClick={() => onOpenChange(false)}>
              {running ? "Downloading…" : "Close"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="stack">
          {fromBoth && <p className="muted">These come from both libraries. They download together and keep their credits.</p>}
          <Select label="Add them to" value={collection} onChange={setCollection} options={options} />
          {collection === NEW && (
            <TextField label="New collection name" value={newName} onChange={(e) => setNewName(e.target.value)} error={nameError} />
          )}
          {start.isError && <ErrorNotice error={start.error} />}
          <div className="dialog-footer">
            <Button onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button variant="primary" onClick={submit} loading={start.isPending}>
              Download
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
