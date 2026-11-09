// Start a media job (loudness, versions, combine), follow its progress, and
// refresh the library when it ends.
import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { keys } from "../../../lib/queries";
import { mediaKeys } from "../../../lib/media";
import { jobRunning, useJob, type Job } from "../../../lib/jobs";
import { ErrorNotice, Notice, ProgressBar } from "../../../components/Notice";

export function useMediaJob<R>(path: string) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob<R>(jobId);
  const start = useMutation({
    mutationFn: (body: unknown) => api.post<{ job_id: string }>(path, body),
    onSuccess: (res) => setJobId(res.job_id),
  });
  const state = job.data?.state;
  useEffect(() => {
    if (state === "done" || state === "failed") {
      void queryClient.invalidateQueries({ queryKey: keys.prerolls });
      void queryClient.invalidateQueries({ queryKey: mediaKeys.loudness });
      void queryClient.invalidateQueries({ queryKey: ["weights"] });
    }
  }, [state, queryClient]);
  const reset = () => {
    setJobId(null);
    start.reset();
  };
  return {
    start,
    job: job.data,
    jobError: job.error,
    running: start.isPending || jobRunning(job.data),
    finished: state === "done" || state === "failed",
    reset,
  };
}

/** Progress while it runs; problems per video; `children` once it's done. */
export function JobProgress({ job, error, label, children }: { job?: Job<unknown>; error?: unknown; label: string; children?: ReactNode }) {
  if (error) return <ErrorNotice error={error} title="Lost track of the job" />;
  if (!job) return null;
  const done = job.state === "done";
  const failed = job.state === "failed";
  return (
    <div className="stack-sm" aria-live="polite">
      {!done && !failed && (
        <>
          <ProgressBar value={job.progress} label={label} />
          <p className="muted small">
            {job.message || "Starting…"}
            {job.total > 1 ? ` (${job.done} of ${job.total})` : ""}
          </p>
        </>
      )}
      {failed && (
        <Notice tone="error" title="That didn't finish">
          {job.message || "Something went wrong while working on the videos. Try again; if it keeps happening, check Logs under Settings, Advanced."}
        </Notice>
      )}
      {done && children}
      {job.errors.length > 0 && (
        <Notice tone="warning" title={job.errors.length === 1 ? "One video had a problem" : `${job.errors.length} videos had problems`}>
          <ul className="plain-list small">
            {job.errors.slice(0, 10).map((e, i) => (
              <li key={`${e.item_id}-${i}`}>{e.message}</li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  );
}
