// Add from a web link: paste a link to one video file and Prerolls Max
// downloads it in the background, then adds it like an upload.
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { api } from "../../lib/api";
import { keys } from "../../lib/queries";
import { describeError } from "../../lib/errors";
import { useJob } from "../../lib/jobs";
import { checkVideoLink } from "../../lib/videoLink";
import { stateFromAnswer, type UploadAnswer, type UploadState } from "../../lib/uploadQueue";
import { Button } from "../../components/Button";
import { TextField } from "../../components/Field";
import { Notice, ProgressBar } from "../../components/Notice";
import { UploadRow } from "./UploadRow";
import { resolveDuplicate } from "./useUploadList";

interface Props {
  /** The collection id to add to ("" for none), or null when its name needs fixing. */
  ensureCollection: () => Promise<string | null>;
  onAdded?: () => void;
  onBusy?: (busy: boolean) => void;
}

type LinkResult = UploadAnswer & { id?: number; source_url?: string };

export function LinkImport({ ensureCollection, onAdded, onBusy }: Props) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<{ message: string; hint?: string }>();
  const [starting, setStarting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [row, setRow] = useState<UploadState>();
  const job = useJob<LinkResult>(jobId);
  const state = job.data?.state;
  const running = Boolean(jobId) && state !== "done" && state !== "failed";

  useEffect(() => onBusy?.(starting || running), [starting, running, onBusy]);

  useEffect(() => {
    if (!job.data || !jobId) return;
    if (job.data.state === "failed") {
      const hint = (job.data.result as { hint?: string } | null)?.hint;
      setError({ message: job.data.message, hint });
      setJobId(null);
    } else if (job.data.state === "done") {
      const next = stateFromAnswer(job.data.result ?? undefined);
      setRow(next);
      if (next.status === "done") {
        void queryClient.invalidateQueries({ queryKey: keys.prerolls });
        onAdded?.();
      }
    }
  }, [job.data, jobId, queryClient, onAdded]);

  const start = async () => {
    const check = checkVideoLink(url);
    if (!check.ok) return setError({ message: check.message ?? "", hint: check.hint });
    setError(undefined);
    setStarting(true);
    try {
      const categoryId = await ensureCollection();
      if (categoryId === null) return;
      const res = await api.post<{ job_id: string }>("/api/library/from-link", {
        url: check.value,
        collection_id: categoryId ? Number(categoryId) : undefined,
      });
      setRow(undefined);
      setJobId(res.job_id);
    } catch (e) {
      // Shown under the link, whatever it is (a refused link, a deleted collection).
      const { message, hint } = describeError(e);
      setError({ message, hint });
    } finally {
      setStarting(false);
    }
  };

  const choose = async (action: "add" | "skip") => {
    if (row?.status !== "duplicate") return;
    setRow({ ...row, busy: action });
    try {
      const res = await resolveDuplicate(row.token, action);
      if (action === "skip") setRow({ status: "skipped", message: `Skipped. It's already in your library as "${row.existing}".` });
      else {
        setRow(stateFromAnswer(res));
        await queryClient.invalidateQueries({ queryKey: keys.prerolls });
        onAdded?.();
      }
    } catch (e) {
      setRow({ status: "refused", message: describeError(e).message });
    }
  };

  const reset = () => {
    setUrl("");
    setJobId(null);
    setRow(undefined);
    setError(undefined);
  };

  const result = job.data?.result;
  const finished = state === "done" && row;
  return (
    <div className="stack">
      <TextField
        label="Link to a video file"
        type="url"
        inputMode="url"
        placeholder="https://example.com/intro.mp4"
        help="A direct link that downloads one file, usually ending in .mp4 or .mkv. Video sites like YouTube and streams don't work."
        value={url}
        onChange={(e) => {
          setUrl(e.target.value);
          if (error) setError(undefined);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !running && !finished) void start();
        }}
        error={error ? `${error.message}${error.hint ? ` ${error.hint}` : ""}` : undefined}
        disabled={running || Boolean(finished)}
      />
      {running && job.data && <ProgressBar value={job.data.progress} label={job.data.message || "Downloading"} />}
      {running && <p className="muted small" aria-live="polite">{job.data?.message ?? "Starting…"}</p>}
      {finished && row && (
        <ul className="upload-list" aria-live="polite">
          <UploadRow name={result?.filename ?? "Video from the link"} state={row} onChoose={choose} />
        </ul>
      )}
      {finished && row?.status === "done" && <Notice tone="success">Added to your library.</Notice>}
      <div className="row">
        {finished ? (
          <Button onClick={reset} disabled={row?.status === "duplicate" && Boolean(row.busy)}>
            Add another link
          </Button>
        ) : (
          <Button variant="primary" icon={<Link2 size={18} aria-hidden="true" />} loading={starting || running} onClick={start}>
            {running ? "Downloading…" : "Add from link"}
          </Button>
        )}
      </div>
    </div>
  );
}
