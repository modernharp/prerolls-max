// "Make a TV-friendly version": a 1080p (or 720p, or 4K) SDR H.264 copy that
// every app plays without converting or switching the TV into HDR mode.
import { useState } from "react";
import { useMediaStatus, type VersionsResult } from "../../../lib/media";
import { plural } from "../../../lib/format";
import { Modal } from "../../../components/Dialog";
import { Button } from "../../../components/Button";
import { Select } from "../../../components/Select";
import { ErrorNotice, Notice } from "../../../components/Notice";
import { JobProgress, useMediaJob } from "./useMediaJob";

const RATES = [
  { value: "source", label: "Same as the original" },
  { value: "23.976", label: "23.976 (most films)" },
  { value: "24", label: "24" },
  { value: "25", label: "25 (UK and Europe TV)" },
  { value: "29.97", label: "29.97 (US TV)" },
  { value: "30", label: "30" },
  { value: "50", label: "50" },
  { value: "59.94", label: "59.94" },
  { value: "60", label: "60" },
];

function Done({ result }: { result: VersionsResult }) {
  return (
    <Notice tone="success" title={result.made.length ? `Made ${plural(result.made.length, "version")}` : "Nothing needed a new version"}>
      <ul className="plain-list small">
        {result.made.map((m) => (
          <li key={`${m.preroll_id}-${m.profile}`}>
            {m.name}: {m.was} → {m.format}
            {m.tone_mapped ? " (HDR colours converted)" : ""}
          </li>
        ))}
        {result.skipped.map((s) => (
          <li key={`s${s.preroll_id}-${s.profile}`} className="muted">
            {s.name}: skipped. {s.why}
          </li>
        ))}
      </ul>
      {result.note && <p className="small">{result.note}</p>}
    </Notice>
  );
}

export function VersionsDialog({ ids, open, onClose }: { ids: number[]; open: boolean; onClose: () => void }) {
  const status = useMediaStatus();
  const [profile, setProfile] = useState("1080p");
  const [rate, setRate] = useState("source");
  const [useInstead, setUseInstead] = useState(true);
  const run = useMediaJob<VersionsResult>("/api/media/versions");
  const close = () => {
    if (!run.running) run.reset();
    onClose();
  };
  const profiles = status.data?.profiles ?? [
    { id: "1080p" as const, label: "1080p SDR" },
    { id: "720p" as const, label: "720p SDR" },
    { id: "2160p" as const, label: "4K SDR" },
  ];

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && close()}
      title={`Make a TV-friendly version of ${plural(ids.length, "intro")}`}
      description="A 4K HDR intro before a 1080p movie can make TVs flick into HDR mode and back, and makes servers convert it on the fly. A matching copy plays everywhere as it is."
    >
      {!run.job && !run.start.isPending ? (
        <div className="stack">
          {status.data && !status.data.ffmpeg && <Notice tone="error" title="This can't run here">{status.data.note}</Notice>}
          <div className="form-grid">
            <Select label="Size" value={profile} onChange={setProfile} options={profiles.map((p) => ({ value: p.id, label: p.label }))} help="1080p suits almost every TV." />
            <Select label="Frames per second" value={rate} onChange={setRate} options={RATES} />
          </div>
          <p className="muted small">H.264 video and stereo AAC sound at 48 kHz. Intros that already match are skipped.</p>
          <label className="checkbox">
            <input type="checkbox" checked={useInstead} onChange={(e) => setUseInstead(e.target.checked)} />
            Play the new version instead of the original (the original is switched off, not deleted)
          </label>
          {run.start.isError && <ErrorNotice error={run.start.error} />}
          <div className="dialog-footer">
            <Button onClick={close}>Cancel</Button>
            <Button
              variant="primary"
              disabled={status.data?.ffmpeg === false}
              onClick={() => run.start.mutate({ preroll_ids: ids, profiles: [profile], frame_rate: rate, use_instead: useInstead, skip_matching: true })}
            >
              Make version
            </Button>
          </div>
        </div>
      ) : (
        <div className="stack">
          <p className="muted small">This takes about as long as the videos are, sometimes longer for 4K. You can close this and come back.</p>
          <JobProgress job={run.job} error={run.jobError} label="Making TV-friendly versions">
            {run.job?.result && <Done result={run.job.result} />}
          </JobProgress>
          <div className="dialog-footer">
            <Button variant={run.finished ? "primary" : "secondary"} onClick={close}>
              {run.finished ? "Done" : "Close and keep going"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
