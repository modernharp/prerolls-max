// "Test connection" for one server: the steps the server checks
// (POST /api/servers/{id}/test), each with what to do when it fails.
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { api } from "../../lib/api";
import type { MediaServer, TestStep } from "../../lib/mediaServers";
import { ErrorNotice } from "../../components/Notice";

const ICON: Record<TestStep["state"] | "running", ReactNode> = {
  running: <Loader2 size={22} className="spinner" aria-hidden="true" />,
  ok: <CheckCircle2 size={22} className="status-ok" aria-hidden="true" />,
  warn: <AlertTriangle size={22} className="status-warn" aria-hidden="true" />,
  fail: <XCircle size={22} className="status-bad" aria-hidden="true" />,
  skipped: <Circle size={22} className="muted" aria-hidden="true" />,
};

const LABEL: Record<TestStep["state"], string> = {
  ok: "Working",
  warn: "Needs a look",
  fail: "Not working",
  skipped: "Skipped until the step above works",
};

/** Runs the test when `run` changes (a counter), and shows the steps. */
export function ServerTestSteps({ server, run }: { server: Pick<MediaServer, "id" | "name">; run: number }) {
  const queryClient = useQueryClient();
  const [steps, setSteps] = useState<TestStep[]>([]);
  const test = useMutation({
    mutationFn: () => api.post<{ steps: TestStep[] }>(`/api/servers/${server.id}/test`, {}, { timeoutMs: 60_000 }),
    onSuccess: async (data) => {
      setSteps(data.steps);
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
    },
  });
  const { mutate } = test;
  useEffect(() => {
    if (run > 0) mutate();
  }, [run, mutate]);

  if (test.isError) return <ErrorNotice error={test.error} onRetry={() => test.mutate()} />;
  if (test.isPending && !steps.length) {
    return (
      <p className="row muted" aria-live="polite">
        {ICON.running} Checking {server.name}…
      </p>
    );
  }
  if (!steps.length) return null;
  return (
    <ol className="check-steps" aria-live="polite" aria-label={`Test results for ${server.name}`}>
      {steps.map((s) => (
        <li key={s.id} className={`check-step ${s.state}`}>
          {test.isPending ? ICON.running : ICON[s.state]}
          <div className="grow">
            <strong>{s.title}</strong>
            <span className="visually-hidden">: {LABEL[s.state]}</span>
            {(s.detail || s.link) && (
              <div className="small">
                {s.detail} {s.link && <Link to={s.link.to}>{s.link.label}</Link>}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
