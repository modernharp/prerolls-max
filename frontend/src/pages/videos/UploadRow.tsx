// One file in the upload list, with its own status, like the upload lists in
// Google Drive or Dropbox: waiting, a progress bar, added, "Not added" with
// the reason, or "Already in your library" with Skip / Add anyway.
import { AlertCircle, CheckCircle2, Copy, X } from "lucide-react";
import { formatSize } from "../../lib/format";
import { describeError } from "../../lib/errors";
import type { UploadState } from "../../lib/uploadQueue";
import { Button, IconButton } from "../../components/Button";
import { ProgressBar } from "../../components/Notice";

interface Props {
  name: string;
  size?: number;
  state?: UploadState;
  onRemove?: () => void;
  onChoose?: (action: "add" | "skip") => void;
}

export function UploadRow({ name, size, state, onRemove, onChoose }: Props) {
  const removable = onRemove && (!state || state.status === "refused" || state.status === "error" || state.status === "waiting");
  return (
    <li className={`upload-row ${state?.status === "refused" ? "upload-row-refused" : ""}`}>
      <div className="row-between">
        <span className="grow upload-name">{name}</span>
        {size !== undefined && <span className="muted small">{formatSize(size)}</span>}
        {state?.status === "done" && <CheckCircle2 size={20} className="status-ok" aria-label="Added" />}
        {removable && (
          <IconButton label={`Remove ${name} from the list`} onClick={onRemove}>
            <X size={18} aria-hidden="true" />
          </IconButton>
        )}
      </div>
      <RowStatus name={name} state={state} onChoose={onChoose} />
    </li>
  );
}

function RowStatus({ name, state, onChoose }: { name: string; state?: UploadState; onChoose?: Props["onChoose"] }) {
  switch (state?.status) {
    case "sending":
      return <ProgressBar value={state.percent} label={`Uploading ${name}`} />;
    case "processing":
      return <p className="muted small">Checking the video and making a thumbnail…</p>;
    case "skipped":
      return <p className="muted small">{state.message}</p>;
    case "refused":
      return (
        <p className="field-error">
          <AlertCircle size={16} aria-hidden="true" /> Not added — {state.message}
        </p>
      );
    case "error": {
      const { message, hint } = describeError(state.error);
      return (
        <p className="field-error">
          <AlertCircle size={16} aria-hidden="true" /> {message} {hint} It's sent again when you press Upload.
        </p>
      );
    }
    case "duplicate":
      return (
        <div className="upload-duplicate" role="group" aria-label={`${name} is already in your library`}>
          <p className="small">
            <Copy size={16} aria-hidden="true" /> Already in your library as "{state.existing}".
          </p>
          <div className="row">
            <Button size="sm" variant="primary" loading={state.busy === "skip"} disabled={Boolean(state.busy)} onClick={() => onChoose?.("skip")}>
              Skip
            </Button>
            <Button size="sm" loading={state.busy === "add"} disabled={Boolean(state.busy)} onClick={() => onChoose?.("add")}>
              Add anyway
            </Button>
          </div>
        </div>
      );
    default:
      return null;
  }
}
