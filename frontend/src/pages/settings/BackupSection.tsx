// Backup & restore.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { ApiError, describeError } from "../../lib/errors";
import { plural } from "../../lib/format";
import { ruleKeys, useSmartSettings, type SmartSettings } from "../../lib/rules";
import { formatDateTime } from "../../lib/format";
import { sendUpload } from "../../lib/uploadQueue";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { Notice } from "../../components/Notice";
import { SwitchRow } from "../../components/Controls";
import { useToast } from "../../components/Toast";

interface RestoreReport {
  smart_features?: Record<string, number>;
  skipped?: string[];
  /** Schedules, playlists and rules that came back as "Name (2)". */
  renamed?: string[];
}

const PARTS: Record<string, [string, string]> = {
  intro_rules: ["rule", "rules"],
  intro_exclusions: ["never-play entry", "never-play entries"],
  watch_folders: ["watch folder", "watch folders"],
  play_history: ["play in the history", "plays in the history"],
};

/** "3 rules, 2 watch folders and the Playback settings" from the restore answer. */
export function restoredText(parts: Record<string, number> = {}): string | null {
  const bits = Object.entries(parts).flatMap(([key, count]) => {
    if (key === "smart_settings") return ["the Playback settings"];
    const words = PARTS[key];
    return words ? [plural(count, words[0], words[1])] : [];
  });
  if (!bits.length) return null;
  const last = bits.pop();
  return bits.length ? `${bits.join(", ")} and ${last}` : (last ?? null);
}

function RestoreSummary({ report, onClose }: { report: RestoreReport; onClose: () => void }) {
  const restored = restoredText(report.smart_features);
  const skipped = report.skipped ?? [];
  const renamed = report.renamed ?? [];
  return (
    <Notice tone={skipped.length ? "warning" : "success"} title="Restored from your backup" action={<Button size="sm" onClick={onClose}>OK</Button>}>
      {restored && <p>Also restored: {restored}.</p>}
      {renamed.length > 0 && (
        <>
          <p>Some names were already taken, so these got a number:</p>
          <ul className="plain-list">
            {renamed.slice(0, 20).map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </>
      )}
      {skipped.length > 0 && (
        <>
          <p>{plural(skipped.length, "thing was", "things were")} left out:</p>
          <ul className="plain-list">
            {skipped.slice(0, 20).map((text) => (
              <li key={text}>{text.charAt(0).toUpperCase() + text.slice(1)}</li>
            ))}
          </ul>
          {skipped.length > 20 && <p className="muted small">And {skipped.length - 20} more.</p>}
        </>
      )}
    </Notice>
  );
}

function HistoryInBackups() {
  const settings = useSmartSettings();
  const queryClient = useQueryClient();
  const toast = useToast();
  const save = useMutation({
    mutationFn: (on: boolean) => api.put<SmartSettings>("/api/smart-settings", { backup_includes_history: on }),
    onSuccess: (data) => queryClient.setQueryData(ruleKeys.smart, data),
    onError: (error) => toast({ tone: "error", title: describeError(error).message, description: describeError(error).hint }),
  });
  if (!settings.data || settings.data.backup_includes_history === undefined) return null;
  return (
    <SwitchRow
      label="Include play history in backups"
      description="Which intros played, for whom and on which app. Off by default, because it can be long and says what people watched."
      checked={Boolean(save.isPending ? save.variables : settings.data.backup_includes_history)}
      disabled={save.isPending}
      onChange={(on) => save.mutate(on)}
    />
  );
}

export function BackupSection() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pickError, setPickError] = useState<string>();
  const [report, setReport] = useState<RestoreReport | null>(null);
  const last = useQuery({ queryKey: ["backup-status"], queryFn: () => api.get<{ last_backup_at: string | null }>("/backup/status") });

  const restore = async () => {
    if (!file) return;
    if (file.name.toLowerCase().endsWith(".json")) {
      let data: unknown;
      try {
        data = JSON.parse(await file.text());
      } catch {
        throw new ApiError({ kind: "invalid", message: "That file isn't a Prerolls Max backup.", hint: "Pick the .json or .zip file you downloaded from this page." });
      }
      setReport(await api.post<RestoreReport>("/restore/database", data, { timeoutMs: 120_000 }));
    } else {
      const form = new FormData();
      form.append("file", file);
      await sendUpload("/restore/files", form).promise;
    }
    await queryClient.invalidateQueries();
    toast({ tone: "success", title: "Restored from your backup" });
    setFile(null);
  };

  return (
    <div className="stack">
      <p className="muted">
        A backup saves your collections, schedules, rules, never-play list, watch folders and settings. The full backup
        also includes the video files, so it can be large. Both hold the keys to your media servers, so keep the file
        somewhere private.
        {last.data?.last_backup_at ? ` Last backup: ${formatDateTime(last.data.last_backup_at)}.` : ""}
      </p>
      <div className="form-actions">
        <a className="btn btn-primary" href="/backup/database" download="prerolls-max-settings.json">
          <Download size={18} aria-hidden="true" /> Download settings backup
        </a>
        {/* A plain form post lets the browser stream a large ZIP straight to disk. */}
        <form ref={formRef} method="post" action="/backup/files">
          <Button type="submit" icon={<Download size={18} aria-hidden="true" />}>
            Download full backup (with videos)
          </Button>
        </form>
      </div>
      <HistoryInBackups />
      <hr className="divider" />
      <h3>Restore</h3>
      <p className="muted">Pick a backup file you downloaded from here (.json or .zip).</p>
      <div className="form-actions">
        <Button icon={<Upload size={18} aria-hidden="true" />} onClick={() => fileRef.current?.click()}>
          Choose backup file
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".json,.zip,application/json,application/zip"
          hidden
          aria-label="Backup file"
          onChange={(e) => {
            const picked = e.target.files?.[0] ?? null;
            e.target.value = "";
            if (picked && !/\.(json|zip)$/i.test(picked.name)) {
              setPickError("Pick a .json or .zip backup file.");
              return;
            }
            setPickError(undefined);
            setFile(picked);
          }}
        />
      </div>
      {pickError && <Notice tone="error">{pickError}</Notice>}
      {report && <RestoreSummary report={report} onClose={() => setReport(null)} />}
      <ConfirmDialog
        open={Boolean(file)}
        onOpenChange={(o) => !o && setFile(null)}
        title={file ? `Restore from "${file.name}"?` : ""}
        body={<p>This replaces your current collections, schedules and settings with the ones in the backup. Download a backup first if you might want them back.</p>}
        confirmLabel="Restore"
        danger
        onConfirm={restore}
      />
    </div>
  );
}
