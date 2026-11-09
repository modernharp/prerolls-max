// Bring a NeXroll setup over: found on this computer, a backup file, or a
// running NeXroll. Every way shows what it found first; then Replace or Merge,
// and a plain report. Videos Prerolls Max can't see get a "where are they now?"
// step. Used in Settings and in the first-run guide.
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderSearch, HardDrive, Server, Upload } from "lucide-react";
import { api } from "../../../lib/api";
import { ApiError, describeError } from "../../../lib/errors";
import { plural } from "../../../lib/format";
import { useJob, type Job } from "../../../lib/jobs";
import {
  missingSentence,
  nexrollKeys,
  previewSummary,
  serverLines,
  useMigrateStatus,
  type ImportMode,
  type ImportReport,
  type MissingVideos,
  type Preview,
  type RelinkResult,
  type SourceResult,
} from "../../../lib/nexroll";
import { sendUpload } from "../../../lib/uploadQueue";
import { Button } from "../../../components/Button";
import { SwitchRow } from "../../../components/Controls";
import { ConfirmDialog } from "../../../components/Dialog";
import { TextField } from "../../../components/Field";
import { ErrorNotice, Loading, Notice, ProgressBar } from "../../../components/Notice";

type Way = "found" | "upload" | "running";

const WAYS: { id: Way; title: string; desc: string; icon: typeof HardDrive }[] = [
  { id: "found", title: "Found on this computer", desc: "NeXroll's data folder, or its old Docker volume.", icon: HardDrive },
  { id: "upload", title: "Upload a NeXroll backup", desc: "The .json or .zip from NeXroll's Backup & Restore.", icon: Upload },
  { id: "running", title: "From a running NeXroll", desc: "Its address, and an API key if its sign-in is on.", icon: Server },
];

function fieldError(error: unknown, field: string): string | undefined {
  return error instanceof ApiError ? error.fields[field] : undefined;
}

/** Waits for a job and hands its result over once. */
function JobProgress<R>({ jobId, label, onDone }: { jobId: string; label: string; onDone: (result: R) => void }) {
  const job = useJob<R>(jobId);
  const handed = useRef(false);
  const data = job.data as Job<R> | undefined;
  if (data?.state === "done" && data.result && !handed.current) {
    handed.current = true;
    queueMicrotask(() => onDone(data.result as R));
  }
  if (job.isError) return <ErrorNotice error={job.error} />;
  if (data?.state === "failed") {
    const hint = (data.result as { hint?: string } | null)?.hint;
    return (
      <Notice tone="error" title={data.message}>
        {hint}
      </Notice>
    );
  }
  if (data?.state === "done") return null;
  return (
    <div className="stack-sm" aria-live="polite">
      <ProgressBar value={data?.progress ?? 0} label={label} />
      <p className="muted small">{data?.message ?? "Starting…"}</p>
    </div>
  );
}

function FoundHere({ onJob }: { onJob: (id: string) => void }) {
  const status = useMigrateStatus();
  const [path, setPath] = useState("");
  const scan = useMutation({
    mutationFn: (body: { path?: string }) => api.post<{ job_id: string }>("/api/migrate/nexroll/scan", body),
    onSuccess: (r) => onJob(r.job_id),
  });
  const found = status.data?.found ?? [];
  const docker = status.data?.platform === "docker";
  return (
    <div className="stack">
      {status.isLoading && <Loading label="Looking for NeXroll's data…" />}
      {found.length > 0 ? (
        <ul className="list">
          {found.map((f) => (
            <li key={f.path} className="list-row">
              <div className="grow">
                <strong>{f.folder}</strong>
                <div className="muted small">NeXroll's database, last changed {new Date(f.modified).toLocaleString()}</div>
              </div>
              <Button size="sm" variant="primary" loading={scan.isPending && scan.variables?.path === f.path} onClick={() => scan.mutate({ path: f.path })}>
                Use this
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        status.data && <p className="muted">Prerolls Max didn't find NeXroll's data in the usual places.</p>
      )}
      <form
        className="stack-sm"
        onSubmit={(e) => {
          e.preventDefault();
          scan.mutate({ path });
        }}
      >
        <TextField
          label="Or type NeXroll's data folder"
          help={
            docker
              ? "Add NeXroll's old data volume to this container first, for example as /nexroll, then type that path."
              : "The folder with nexroll.db in it, like C:\\ProgramData\\NeXroll or /srv/nexroll/data."
          }
          placeholder={docker ? "/nexroll" : "C:\\ProgramData\\NeXroll"}
          value={path}
          onChange={(e) => setPath(e.target.value)}
          error={fieldError(scan.error, "path")}
          autoComplete="off"
        />
        <div className="form-actions">
          <Button type="submit" icon={<FolderSearch size={18} aria-hidden="true" />} loading={scan.isPending && scan.variables?.path === path} disabled={!path.trim()}>
            Look here
          </Button>
        </div>
      </form>
      {scan.isError && !fieldError(scan.error, "path") && <ErrorNotice error={scan.error} />}
      <p className="muted small">NeXroll's file is only read, never changed.</p>
    </div>
  );
}

function UploadBackup({ onJob }: { onJob: (id: string) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const send = async (file: File) => {
    setError(null);
    if (!/\.(json|zip)$/i.test(file.name)) {
      setError(new ApiError({ kind: "invalid", message: "Pick the .json or .zip file NeXroll's Backup & Restore made." }));
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setProgress(0);
    try {
      const answer = (await sendUpload("/api/migrate/nexroll/upload", form, { onProgress: setProgress }).promise) as { job_id: string };
      onJob(answer.job_id);
    } catch (e) {
      setError(e);
    } finally {
      setProgress(null);
    }
  };
  return (
    <div className="stack">
      <p className="muted">
        In NeXroll, open Settings &gt; Backup &amp; Restore. <strong>Download Database Backup</strong> gives a small .json;{" "}
        <strong>Download System Backup</strong> gives a .zip with the videos too.
      </p>
      <div className="form-actions">
        <Button variant="primary" icon={<Upload size={18} aria-hidden="true" />} onClick={() => fileRef.current?.click()} loading={progress !== null}>
          Choose backup file
        </Button>
        <input
          ref={fileRef}
          type="file"
          hidden
          aria-label="NeXroll backup file"
          accept=".json,.zip,application/json,application/zip"
          onChange={(e) => {
            const picked = e.target.files?.[0];
            e.target.value = "";
            if (picked) void send(picked);
          }}
        />
      </div>
      {progress !== null && <ProgressBar value={progress} label="Uploading the backup" />}
      {error ? <ErrorNotice error={error} /> : null}
    </div>
  );
}

function FromRunning({ onJob }: { onJob: (id: string) => void }) {
  const [url, setUrl] = useState("http://localhost:9393");
  const [key, setKey] = useState("");
  const fetchIt = useMutation({
    mutationFn: () => api.post<{ job_id: string }>("/api/migrate/nexroll/fetch", { url, api_key: key || undefined }),
    onSuccess: (r) => onJob(r.job_id),
  });
  return (
    <form
      className="stack-sm"
      onSubmit={(e) => {
        e.preventDefault();
        fetchIt.mutate();
      }}
    >
      <TextField
        label="NeXroll's address"
        help="If Prerolls Max runs in Docker, use the computer's IP address instead of localhost."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        error={fieldError(fetchIt.error, "url")}
        autoComplete="off"
      />
      <TextField
        label="NeXroll API key"
        optional
        type="password"
        help="Only needed when NeXroll's sign-in is on. Make one in NeXroll under Settings > API Keys; read only is enough. Keys for your media servers stay in NeXroll when you use one."
        value={key}
        onChange={(e) => setKey(e.target.value)}
        error={fieldError(fetchIt.error, "api_key")}
        autoComplete="off"
      />
      <div className="form-actions">
        <Button type="submit" variant="primary" loading={fetchIt.isPending}>
          Connect to NeXroll
        </Button>
      </div>
      {fetchIt.isError && !fieldError(fetchIt.error, "url") && !fieldError(fetchIt.error, "api_key") && <ErrorNotice error={fetchIt.error} />}
      {fetchIt.isError && fieldError(fetchIt.error, "api_key") && describeError(fetchIt.error).hint && (
        <p className="muted small">{describeError(fetchIt.error).hint}</p>
      )}
    </form>
  );
}

function PreviewCard({ result, onImported, onCancel }: { result: SourceResult; onImported: (r: ImportReport) => void; onCancel: () => void }) {
  const p: Preview = result.preview;
  const [mode, setMode] = useState<ImportMode>(p.suggested_mode);
  const [keys, setKeys] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () =>
      api.post<{ job_id: string }>("/api/migrate/nexroll/import", {
        source_id: result.source_id,
        mode,
        include_keys: keys,
        confirm_replace: mode === "replace",
      }),
    onSuccess: (r) => setJobId(r.job_id),
  });
  const missing = missingSentence(p.missing);
  const servers = serverLines(p);
  const taken = [...p.names_taken.schedules, ...p.names_taken.playlists];
  return (
    <section className="card stack" aria-labelledby="nx-preview-title">
      <h3 id="nx-preview-title">What NeXroll has</h3>
      <p>{previewSummary(p)}.</p>
      {servers.length > 0 && (
        <div>
          <p className="field-label">Media servers</p>
          <ul className="plain-list">
            {servers.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {p.counts.videos_in_zip > 0 && <p className="muted small">The backup holds {plural(p.counts.videos_in_zip, "video file")}; they're copied into your intro folder.</p>}
      {missing && (
        <Notice tone="warning" title={`${plural(p.missing.count, "video")} can't be found here yet`}>
          <p>{missing} You can do that right after the import.</p>
          {p.missing.examples.length > 0 && <p className="muted small">For example: {p.missing.examples.join(", ")}.</p>}
        </Notice>
      )}
      {p.left_behind.length > 0 && (
        <div>
          <p className="field-label">Stays in NeXroll</p>
          <ul className="plain-list">
            {p.left_behind.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {p.source.keys_left_out && (
        <p className="muted small">NeXroll doesn't hand out media server keys to an API key, so you'll add those keys on the Media Servers page.</p>
      )}

      <fieldset className="plain-fieldset">
        <legend className="field-label">How to bring it in</legend>
        <div className="choice-grid">
          <label className="choice">
            <input type="radio" name="nx-mode" value="replace" checked={mode === "replace"} onChange={() => setMode("replace")} />
            <span>
              <span className="choice-title">Replace{p.suggested_mode === "replace" ? " (suggested)" : ""}</span>
              <span className="choice-desc">Swap what's in Prerolls Max for NeXroll's setup, settings included. For a fresh install.</span>
            </span>
          </label>
          <label className="choice">
            <input type="radio" name="nx-mode" value="merge" checked={mode === "merge"} onChange={() => setMode("merge")} />
            <span>
              <span className="choice-title">Merge{p.suggested_mode === "merge" ? " (suggested)" : ""}</span>
              <span className="choice-desc">Add what's missing and keep what you have. Your settings stay as they are.</span>
            </span>
          </label>
        </div>
      </fieldset>
      {mode === "merge" && (p.names_taken.collections.length > 0 || taken.length > 0) && (
        <p className="muted small">
          {p.names_taken.collections.length > 0 && `Collections you already have (${p.names_taken.collections.join(", ")}) are joined, not doubled. `}
          {taken.length > 0 && `Schedules or playlists whose name is taken (${taken.join(", ")}) come in as "Name (2)" unless they're the same.`}
        </p>
      )}
      {p.keys.length > 0 && (
        <SwitchRow
          label="Bring the keys too"
          description={`NeXroll's data has ${p.keys.join(", ")}. Switch this off to type them again yourself.`}
          checked={keys}
          onChange={setKeys}
        />
      )}
      {!jobId && (
        <div className="form-actions">
          <Button variant="primary" loading={start.isPending} onClick={() => (mode === "replace" && !p.library_empty ? setConfirm(true) : start.mutate())}>
            {mode === "replace" ? "Replace with NeXroll's setup" : "Merge NeXroll's setup in"}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      )}
      {start.isError && <ErrorNotice error={start.error} />}
      {jobId && <JobProgress<ImportReport> jobId={jobId} label="Bringing your setup over" onDone={onImported} />}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Replace your Prerolls Max setup?"
        body={
          <p>
            Your current collections, intro videos, schedules, playlists and settings are removed and NeXroll's take their place. The video files
            themselves stay on disk. Download a backup first (Settings &gt; Backup and restore) if you might want them back.
          </p>
        }
        confirmLabel="Replace"
        danger
        onConfirm={() => start.mutateAsync().then(() => undefined)}
      />
    </section>
  );
}

export function RelinkForm({ missing, onDone }: { missing: MissingVideos; onDone?: () => void }) {
  const queryClient = useQueryClient();
  const [from, setFrom] = useState(missing.folder ?? "");
  const [to, setTo] = useState("");
  const relink = useMutation({
    mutationFn: () => api.post<RelinkResult>("/api/migrate/nexroll/relink", { from_folder: from, to_folder: to }, { timeoutMs: 120_000 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.status });
      await queryClient.invalidateQueries({ queryKey: ["prerolls"] });
      onDone?.();
    },
  });
  const sentence = missingSentence(missing);
  return (
    <form
      className="stack-sm"
      onSubmit={(e) => {
        e.preventDefault();
        relink.mutate();
      }}
    >
      {sentence && <p>{sentence}</p>}
      <TextField label="Where NeXroll kept them" value={from} onChange={(e) => setFrom(e.target.value)} error={fieldError(relink.error, "from_folder")} autoComplete="off" />
      <TextField
        label="Where they are now"
        help="A folder Prerolls Max can see. In Docker, the path inside the container, like /media/prerolls."
        placeholder="/media/prerolls"
        value={to}
        onChange={(e) => setTo(e.target.value)}
        error={fieldError(relink.error, "to_folder")}
        autoComplete="off"
      />
      <div className="form-actions">
        <Button type="submit" variant="primary" loading={relink.isPending} disabled={!to.trim()}>
          Find them
        </Button>
      </div>
      {relink.isError && !fieldError(relink.error, "to_folder") && !fieldError(relink.error, "from_folder") && <ErrorNotice error={relink.error} />}
      {relink.data && (
        <Notice tone={relink.data.still_missing ? "warning" : "success"} title={relink.data.message}>
          {relink.data.examples.length > 0 && <p>Still missing: {relink.data.examples.join(", ")}.</p>}
        </Notice>
      )}
    </form>
  );
}

function ReportCard({ report, onAgain }: { report: ImportReport; onAgain: () => void }) {
  return (
    <section className="card stack" aria-labelledby="nx-report-title">
      <h3 id="nx-report-title">Done</h3>
      <Notice tone={report.skipped.length || report.missing.count ? "warning" : "success"} title={report.message}>
        <p>{report.settings === "replaced" ? "NeXroll's settings are in use now. Your sign-in stayed as it was." : "Your Prerolls Max settings stayed as they were."}</p>
        {report.videos_copied > 0 && <p>Copied {plural(report.videos_copied, "video file")} from the backup into your intro folder.</p>}
        {report.keys_imported.length > 0 && <p>Brought over {report.keys_imported.join(", ")}.</p>}
      </Notice>
      {report.notes.length > 0 && (
        <ul className="plain-list">
          {report.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {report.renamed.length > 0 && (
        <>
          <p>Some names were taken, so these got a number:</p>
          <ul className="plain-list">
            {report.renamed.slice(0, 20).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
      {report.skipped.length > 0 && (
        <>
          <p>{plural(report.skipped.length, "thing was", "things were")} left out:</p>
          <ul className="plain-list">
            {report.skipped.slice(0, 20).map((n) => (
              <li key={n}>{n.charAt(0).toUpperCase() + n.slice(1)}</li>
            ))}
          </ul>
        </>
      )}
      {report.missing.count > 0 && <RelinkForm missing={report.missing} />}
      <p className="muted small">
        Next: stop NeXroll if it still runs, remove its plugin from Jellyfin or Emby, and install the Prerolls Max plugin. The{" "}
        <Link to="/help/moving-from-nexroll">Moving from NeXroll</Link> help has each step.
      </p>
      <div className="form-actions">
        <Button variant="ghost" onClick={onAgain}>
          Import something else
        </Button>
      </div>
    </section>
  );
}

export function NexrollImport() {
  const queryClient = useQueryClient();
  const [way, setWay] = useState<Way>("found");
  const [jobId, setJobId] = useState<string | null>(null);
  const [source, setSource] = useState<SourceResult | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const status = useMigrateStatus();
  const waiting = status.data?.import.waiting;
  const reset = () => {
    setJobId(null);
    setSource(null);
    setReport(null);
  };

  if (report) return <ReportCard report={report} onAgain={reset} />;
  if (source)
    return (
      <PreviewCard
        result={source}
        onCancel={reset}
        onImported={async (r) => {
          setReport(r);
          await queryClient.invalidateQueries();
        }}
      />
    );
  return (
    <div className="stack">
      {waiting && waiting.count > 0 && (
        <Notice tone="warning" title={`${plural(waiting.count, "imported video")} still can't be found`}>
          <RelinkForm missing={waiting} />
        </Notice>
      )}
      <div className="choice-grid" role="radiogroup" aria-label="Where NeXroll's setup is">
        {WAYS.map(({ id, title, desc, icon: Icon }) => (
          <label key={id} className="choice">
            <input type="radio" name="nx-way" value={id} checked={way === id} onChange={() => { setWay(id); setJobId(null); }} />
            <span>
              <span className="choice-title">
                <Icon size={16} aria-hidden="true" /> {title}
              </span>
              <span className="choice-desc">{desc}</span>
            </span>
          </label>
        ))}
      </div>
      {!jobId && way === "found" && <FoundHere onJob={setJobId} />}
      {!jobId && way === "upload" && <UploadBackup onJob={setJobId} />}
      {!jobId && way === "running" && <FromRunning onJob={setJobId} />}
      {jobId && (
        <>
          <JobProgress<SourceResult> jobId={jobId} label="Reading NeXroll's setup" onDone={setSource} />
          <div className="form-actions">
            <Button variant="ghost" onClick={() => setJobId(null)}>
              Back
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
