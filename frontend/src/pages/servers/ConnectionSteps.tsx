// "Test connection", one step at a time. A failed step says what to do.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Loader2, XCircle, AlertTriangle } from "lucide-react";
import { api } from "../../lib/api";
import { describeError } from "../../lib/errors";
import { SERVER_NAMES, type ServerCapabilities, type ServerType } from "../../lib/capabilities";
import type { ServerStatus } from "../../lib/types";
import { Button } from "../../components/Button";

type StepState = "waiting" | "running" | "ok" | "warn" | "fail" | "skipped";

interface StepResult {
  state: StepState;
  detail?: ReactNode;
}

interface StepDef {
  title: string;
  run: (ctx: { status?: ServerStatus }) => Promise<StepResult>;
}

const authProblem = (text = "") => /token|api key|unauthori|forbidden|401|403|sign|credential|turned down/i.test(text);

function steps(type: ServerType): StepDef[] {
  const name = SERVER_NAMES[type];
  const statusStep = async (ctx: { status?: ServerStatus }): Promise<StepResult> => {
    try {
      ctx.status = await api.get<ServerStatus>(`/${type}/status`, undefined, { timeoutMs: 20_000 });
    } catch (error) {
      return { state: "fail", detail: describeError(error).message };
    }
    const s = ctx.status;
    if (s.connected || authProblem(s.message ?? s.error)) return { state: "ok" };
    if (!s.url) return { state: "fail", detail: `${name} isn't set up yet. Fill in the form above and connect.` };
    return {
      state: "fail",
      detail: `${name} didn't answer at ${s.url}. Check that ${name} is running, and that the address and port are right. If Prerolls Max runs in Docker, use the computer's IP address instead of "localhost".`,
    };
  };
  const signedIn: StepDef = {
    title: `Signed in to ${name}`,
    run: async ({ status }) =>
      status?.connected
        ? { state: "ok" }
        : {
            state: "fail",
            detail:
              type === "plex"
                ? "Plex turned down the sign-in. Sign in with Plex again, or paste a fresh token under Other ways."
                : `${name} turned down the API key. Make a new one in ${name}'s Dashboard, under API Keys, and paste it in.`,
          },
  };
  if (type === "plex") {
    return [
      { title: "Prerolls Max can reach Plex", run: statusStep },
      signedIn,
      {
        title: "Plex can see your intro folder",
        run: async () => {
          try {
            const r = await api.get<{ reachable?: boolean; action?: string; value?: string; message?: string }>("/plex/preroll-check", undefined, { timeoutMs: 40_000 });
            if (r.reachable === false) return { state: "fail", detail: "Plex stopped answering during the check. Try again in a minute." };
            if (!r.value) return { state: "warn", detail: "Nothing has been sent to Plex yet, so there's nothing to check. Make a schedule or turn on default intros, then test again." };
            if (r.action === "ok") return { state: "ok" };
            return {
              state: "warn",
              detail: (
                <>
                  Plex can't find the intro files where Prerolls Max says they are. This is common when either one runs
                  in Docker. <Link to="/settings/advanced/folder-mapping">Set up folder mapping</Link>.
                </>
              ),
            };
          } catch (error) {
            return { state: "warn", detail: describeError(error).message };
          }
        },
      },
    ];
  }
  return [
    { title: `Prerolls Max can reach ${name}`, run: statusStep },
    signedIn,
    {
      title: `The Prerolls Max plugin is installed in ${name}`,
      run: async () => {
        try {
          const r = await api.get<{ detected?: boolean; version?: string }>(`/${type}/plugin/detect`, undefined, { timeoutMs: 20_000 });
          if (r.detected) return { state: "ok", detail: r.version ? `Version ${r.version}` : undefined };
          return {
            state: "fail",
            detail: (
              <>
                {name} doesn't have the plugin yet. Without it, {name} can't ask which intro to play. Follow the
                plugin steps on <Link to="/servers">Media Servers</Link>.
              </>
            ),
          };
        } catch (error) {
          return { state: "fail", detail: describeError(error).message };
        }
      },
    },
    {
      title: "The plugin has asked Prerolls Max for an intro",
      run: async () => {
        try {
          // /plugin/* needs the plugin's own key; the capabilities say when it last asked.
          const caps = await api.get<{ servers: ServerCapabilities[] }>("/api/capabilities");
          const plugin = caps.servers.find((x) => x.type === type)?.plugin;
          if (plugin?.connected) return { state: "ok", detail: plugin.version ? `Plugin ${plugin.version}` : undefined };
          return {
            state: "warn",
            detail: `Not yet. Play any movie in ${name}; the plugin asks for an intro when it starts.`,
          };
        } catch (error) {
          return { state: "warn", detail: describeError(error).message };
        }
      },
    },
  ];
}

const ICON: Record<StepState, ReactNode> = {
  waiting: <Circle size={22} className="muted" aria-hidden="true" />,
  running: <Loader2 size={22} className="spinner" aria-hidden="true" />,
  ok: <CheckCircle2 size={22} className="status-ok" aria-hidden="true" />,
  warn: <AlertTriangle size={22} className="status-warn" aria-hidden="true" />,
  fail: <XCircle size={22} className="status-bad" aria-hidden="true" />,
  skipped: <Circle size={22} className="muted" aria-hidden="true" />,
};

const LABEL: Record<StepState, string> = {
  waiting: "Not checked yet",
  running: "Checking",
  ok: "Working",
  warn: "Needs a look",
  fail: "Not working",
  skipped: "Skipped until the step above works",
};

/** `button`: show its own Test connection button (off where the page already has one). */
export function ConnectionSteps({ type, autoRun, button = true }: { type: ServerType; autoRun?: number; button?: boolean }) {
  const defs = steps(type);
  const [results, setResults] = useState<StepResult[]>(() => defs.map(() => ({ state: "waiting" })));
  const [running, setRunning] = useState(false);
  const queryClient = useQueryClient();

  const run = useCallback(async () => {
    const list = steps(type);
    setRunning(true);
    const ctx: { status?: ServerStatus } = {};
    const out: StepResult[] = list.map(() => ({ state: "waiting" }));
    let failed = false;
    for (let i = 0; i < list.length; i += 1) {
      if (failed) {
        out[i] = { state: "skipped" };
        continue;
      }
      out[i] = { state: "running" };
      setResults([...out]);
      const step = list[i];
      out[i] = step ? await step.run(ctx) : { state: "skipped" };
      if (out[i]?.state === "fail") failed = true;
      setResults([...out]);
    }
    setRunning(false);
    void queryClient.invalidateQueries({ queryKey: ["capabilities"] });
  }, [type, queryClient]);

  useEffect(() => {
    if (autoRun) void run();
  }, [autoRun, run]);

  return (
    <div className="stack">
      <ol className="check-steps" aria-live="polite">
        {defs.map((d, i) => {
          const r = results[i] ?? { state: "waiting" as const };
          return (
            <li key={d.title} className={`check-step ${r.state}`}>
              {ICON[r.state]}
              <div className="grow">
                <strong>{d.title}</strong>
                <span className="visually-hidden">: {LABEL[r.state]}</span>
                {r.detail && <div className="small">{r.detail}</div>}
              </div>
            </li>
          );
        })}
      </ol>
      {button && (
        <div>
          <Button onClick={run} loading={running}>
            Test connection
          </Button>
        </div>
      )}
    </div>
  );
}
