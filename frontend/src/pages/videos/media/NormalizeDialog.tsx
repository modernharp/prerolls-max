// "Even out loudness": bring intros to the loudness target, as a new version
// (the original stays, switched off) or by replacing the file (the original
// goes to Trash).
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSmartSettings } from "../../../lib/rules";
import type { NormalizeResult } from "../../../lib/media";
import { plural } from "../../../lib/format";
import { Modal } from "../../../components/Dialog";
import { Button } from "../../../components/Button";
import { ErrorNotice, Notice } from "../../../components/Notice";
import { JobProgress, useMediaJob } from "./useMediaJob";

interface Props {
  ids: number[];
  open: boolean;
  onClose: () => void;
}

function Done({ result }: { result: NormalizeResult }) {
  return (
    <Notice tone="success" title={`Evened out ${plural(result.items.length, "intro")} to ${result.target_lufs} LUFS`}>
      <ul className="plain-list small">
        {result.items.map((i) => (
          <li key={i.preroll_id}>
            {i.name}: {i.before_lufs.toFixed(1)} → {i.after_lufs?.toFixed(1) ?? "?"} LUFS
            {i.original_in_trash ? " (the original is in Trash)" : ""}
          </li>
        ))}
      </ul>
      {result.mode === "new_version" && <p className="small">Each new version shows under its original on Your videos.</p>}
    </Notice>
  );
}

export function NormalizeDialog({ ids, open, onClose }: Props) {
  const settings = useSmartSettings();
  const [mode, setMode] = useState<"new_version" | "replace">("new_version");
  const [useInstead, setUseInstead] = useState(true);
  const run = useMediaJob<NormalizeResult>("/api/media/loudness/normalize");
  const target = settings.data?.loudness_target_lufs ?? -23;
  // Closing while it runs keeps following it, so reopening shows the progress.
  const close = () => {
    if (!run.running) run.reset();
    onClose();
  };

  return (
    <Modal open={open} onOpenChange={(o) => !o && close()} title={`Even out loudness of ${plural(ids.length, "intro")}`} description={`Brings them to ${target} LUFS, your target in Settings, Playback.`}>
      {!run.job && !run.start.isPending ? (
        <div className="stack">
          <fieldset className="plain-fieldset">
            <legend className="field-label">What happens to the result</legend>
            <div className="choice-grid">
              <label className="choice">
                <input type="radio" name="norm-mode" checked={mode === "new_version"} onChange={() => setMode("new_version")} />
                <span>
                  <span className="choice-title">Make a new version</span>
                  <span className="choice-desc">The original stays in your library, so you can switch back.</span>
                </span>
              </label>
              <label className="choice">
                <input type="radio" name="norm-mode" checked={mode === "replace"} onChange={() => setMode("replace")} />
                <span>
                  <span className="choice-title">Replace the file</span>
                  <span className="choice-desc">Saves space. The original file goes to Trash.</span>
                </span>
              </label>
            </div>
          </fieldset>
          {mode === "new_version" ? (
            <label className="checkbox">
              <input type="checkbox" checked={useInstead} onChange={(e) => setUseInstead(e.target.checked)} />
              Play the new version instead of the original (it takes the original's place in its collections)
            </label>
          ) : (
            <Notice tone="warning" title="The original file goes to Trash">
              You can get it back from <Link to="/settings/advanced/trash">Trash</Link> for 30 days. Only an admin can replace files.
            </Notice>
          )}
          {run.start.isError && <ErrorNotice error={run.start.error} />}
          <div className="dialog-footer">
            <Button onClick={close}>Cancel</Button>
            <Button variant={mode === "replace" ? "danger" : "primary"} onClick={() => run.start.mutate({ preroll_ids: ids, mode, use_instead: useInstead })}>
              {mode === "replace" ? "Replace and even out" : "Even out"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="stack">
          <p className="muted small">Each intro is measured, then adjusted in one steady step, so it keeps its punch. The picture isn't touched. You can close this and come back.</p>
          <JobProgress job={run.job} error={run.jobError} label="Evening out loudness">
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
