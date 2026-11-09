// Advanced > System and updates: version, update checks, the tools Prerolls
// Max relies on, and a diagnostics file for bug reports.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, XCircle } from "lucide-react";
import { api } from "../../../lib/api";
import { formatDateTime } from "../../../lib/format";
import { Select } from "../../../components/Select";
import { Button } from "../../../components/Button";
import { ErrorNotice, Loading, Notice } from "../../../components/Notice";

interface UpdateCheck {
  success: boolean;
  error?: string;
  update_available?: boolean;
  current_version?: string;
  latest_version?: string;
  html_url?: string;
  published_at?: string;
}

interface UpdateSettings {
  check_interval: string;
  last_check: string | null;
}

interface InstallInfo {
  supported: boolean;
  message?: string;
  current_version?: string;
}

interface Dependency {
  available: boolean;
  version: string | null;
  description: string;
}

const TOOLS: Record<string, string> = {
  ffmpeg: "FFmpeg, for thumbnails, lengths and the video maker",
  ffprobe: "FFprobe, for reading video details",
  yt_dlp: "yt-dlp, for downloading movie trailers",
  deno: "Deno, helps yt-dlp with YouTube",
  node: "Node.js, runs the YouTube PO token helper",
};

function shortVersion(text: string | null): string {
  if (!text) return "";
  const m = /(\d+(?:\.\d+)+[\w.-]*)/.exec(text);
  return m?.[1] ?? text.slice(0, 40);
}

function Updates() {
  const queryClient = useQueryClient();
  const version = useQuery({ queryKey: ["version"], queryFn: () => api.get<{ api_version: string }>("/system/version") });
  const settings = useQuery({ queryKey: ["update-settings"], queryFn: () => api.get<UpdateSettings>("/update/settings") });
  const install = useQuery({ queryKey: ["update-install"], queryFn: () => api.get<InstallInfo>("/update/install") });
  const check = useMutation({ mutationFn: () => api.post<UpdateCheck>("/update/check", {}, { timeoutMs: 30_000 }) });
  const interval = useMutation({
    mutationFn: (check_interval: string) => api.put("/update/settings", { check_interval }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["update-settings"] }),
  });
  const result = check.data;
  const notSetUp = result && !result.success && /PMAX_UPDATE_REPO/.test(result.error ?? "");
  return (
    <div className="stack">
      <dl className="facts">
        <dt>Version</dt>
        <dd>{version.data?.api_version ?? "…"}</dd>
        <dt>Last checked</dt>
        <dd>{settings.data?.last_check ? formatDateTime(settings.data.last_check) : "Never"}</dd>
      </dl>
      <div>
        <Button onClick={() => check.mutate()} loading={check.isPending}>
          Check for updates
        </Button>
      </div>
      {check.isError && <ErrorNotice error={check.error} />}
      {notSetUp && (
        <Notice tone="info" title="Update checks are off for this copy">
          <p>
            Prerolls Max doesn't know where its releases are published yet. Whoever runs it can turn checks on by setting
            PMAX_UPDATE_REPO to the GitHub repository that publishes releases, then restarting it.
          </p>
        </Notice>
      )}
      {result && !result.success && !notSetUp && <Notice tone="warning">{result.error}</Notice>}
      {result?.success &&
        (result.update_available ? (
          <Notice tone="success" title={`Version ${result.latest_version} is out`}>
            <p>
              You have {result.current_version}.{" "}
              {result.html_url && (
                <a href={result.html_url} target="_blank" rel="noreferrer noopener">
                  See what's new
                </a>
              )}
            </p>
            {install.data && !install.data.supported && <p className="small">{install.data.message} With Docker, pull the new image and restart the container.</p>}
          </Notice>
        ) : (
          <Notice tone="success">You have the newest version ({result.current_version}).</Notice>
        ))}
      <div className="toolbar-select">
        <Select
          label="Check automatically"
          value={settings.data?.check_interval ?? "daily"}
          onChange={(v) => interval.mutate(v)}
          options={[
            { value: "never", label: "Never" },
            { value: "startup", label: "When Prerolls Max starts" },
            { value: "daily", label: "Once a day" },
            { value: "weekly", label: "Once a week" },
          ]}
        />
      </div>
      {interval.isError && <ErrorNotice error={interval.error} />}
    </div>
  );
}

function Tools() {
  const deps = useQuery({
    queryKey: ["dependencies"],
    queryFn: async () => (await api.get<{ dependencies: Record<string, Dependency> }>("/system/dependencies", undefined, { timeoutMs: 30_000 })).dependencies,
  });
  if (deps.isLoading) return <Loading />;
  if (deps.isError) return <ErrorNotice error={deps.error} onRetry={() => deps.refetch()} />;
  return (
    <ul className="check-steps">
      {Object.entries(TOOLS).map(([key, label]) => {
        const d = deps.data?.[key];
        if (!d) return null;
        return (
          <li key={key} className="check-step">
            {d.available ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <XCircle size={20} className="status-warn" aria-hidden="true" />}
            <div className="grow">
              <strong>{label}</strong>
              <div className="muted small">{d.available ? `Installed${d.version ? `, ${shortVersion(d.version)}` : ""}` : "Not installed"}</div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SystemPage() {
  return (
    <div className="stack">
      <section className="card stack" aria-labelledby="sys-up">
        <h2 id="sys-up">Updates</h2>
        <Updates />
      </section>
      <section className="card stack" aria-labelledby="sys-tools">
        <h2 id="sys-tools">Tools Prerolls Max uses</h2>
        <Tools />
      </section>
      <section className="card stack" aria-labelledby="sys-diag">
        <h2 id="sys-diag">Diagnostics</h2>
        <p className="muted">
          A zip file with recent logs and settings, for a bug report. Passwords, tokens and API keys are left out.
        </p>
        <div>
          <a className="btn" href="/diagnostics/bundle" download>
            <Download size={18} aria-hidden="true" /> Download diagnostics
          </a>
        </div>
      </section>
      <section className="card stack" aria-labelledby="sys-restart">
        <h2 id="sys-restart">Restarting</h2>
        <p className="muted">
          Prerolls Max can't restart itself from here. Restart it where it runs: with Docker, restart the container; on
          Windows, use the Prerolls Max icon in the system tray; on Linux, restart its service.
        </p>
      </section>
    </div>
  );
}
