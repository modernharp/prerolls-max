// Background jobs (GET /api/jobs/{id}): media tools, community downloads and
// list refreshes report progress here until they finish.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export interface Job<R = unknown> {
  id: string;
  kind: string;
  state: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  done: number;
  total: number;
  errors: { item_id: string | null; message: string }[];
  result: R | null;
}

export function useJob<R = unknown>(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    enabled: Boolean(jobId),
    queryFn: () => api.get<Job<R>>(`/api/jobs/${jobId}`),
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.state) ? false : 1000),
  });
}

export const jobRunning = (job?: Job<unknown>) => Boolean(job && job.state !== "done" && job.state !== "failed");
