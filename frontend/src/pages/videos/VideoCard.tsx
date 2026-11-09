import { useState } from "react";
import { Film, Layers, Pencil, Play, Trash2 } from "lucide-react";
import { formatDuration, formatSize, videoName } from "../../lib/format";
import { thumbnailUrl, videoUrl } from "../../lib/queries";
import { weightLabel } from "../../lib/validateSmart";
import type { Preroll } from "../../lib/types";
import { IconButton } from "../../components/Button";
import { Modal } from "../../components/Dialog";
import { Tip } from "../../components/Controls";

export function Thumb({ preroll }: { preroll: Preroll }) {
  const [broken, setBroken] = useState(false);
  const src = thumbnailUrl(preroll);
  if (!src || broken) {
    return (
      <div className="thumb thumb-empty" aria-hidden="true">
        <Film size={32} />
      </div>
    );
  }
  return <img className="thumb" src={src} alt="" loading="lazy" onError={() => setBroken(true)} />;
}

export function PreviewDialog({ preroll, onClose }: { preroll: Preroll | null; onClose: () => void }) {
  return (
    <Modal open={Boolean(preroll)} onOpenChange={(o) => !o && onClose()} title={preroll ? videoName(preroll) : ""} wide>
      {preroll && (
        <video className="player" src={videoUrl(preroll)} controls autoPlay playsInline>
          Your browser can't play this video here. It may still play on your media server.
        </video>
      )}
    </Modal>
  );
}

export interface LoudnessBadge {
  label: string;
  tone: "success" | "warning" | "neutral" | "danger";
  detail: string;
}

/** "Too loud", with the measured level in a tooltip. */
export function LoudnessTag({ info }: { info?: LoudnessBadge }) {
  if (!info) return null;
  const cls = info.tone === "neutral" ? "badge" : `badge badge-${info.tone}`;
  return (
    <Tip content={info.detail}>
      <button type="button" className={cls} aria-label={`${info.label}. ${info.detail}`}>
        {info.label}
      </button>
    </Tip>
  );
}

interface CardProps {
  preroll: Preroll;
  versions?: Preroll[];
  loudness?: (p: Preroll) => LoudnessBadge | undefined;
  selected?: boolean;
  onSelect?: () => void;
  onPreview: (p: Preroll) => void;
  onEdit: () => void;
  onDelete: (p: Preroll) => void;
}

export function VideoCard({ preroll, versions = [], loudness, selected, onSelect, onPreview, onEdit, onDelete }: CardProps) {
  const name = videoName(preroll);
  const off = preroll.enabled === false;
  const weight = preroll.weight ?? 5;
  return (
    <li className={`video-card ${selected ? "selected" : ""}`}>
      <button type="button" className="thumb-button" onClick={() => onPreview(preroll)} aria-label={`Play ${name}`}>
        <Thumb preroll={preroll} />
        <span className="thumb-play" aria-hidden="true">
          <Play size={28} />
        </span>
        {preroll.duration ? <span className="thumb-length">{formatDuration(preroll.duration)}</span> : null}
      </button>
      <div className="video-body">
        <h3 className="video-name" title={name}>
          {name}
        </h3>
        <div className="video-meta">
          {preroll.categories.length ? (
            preroll.categories.map((c) => (
              <span key={c.id} className="badge">
                {c.name}
              </span>
            ))
          ) : (
            <span className="muted small">Not in a collection</span>
          )}
          {off && (
            <span className="badge badge-warning" title="Switched off when a version took its place">
              Off{versions.some((v) => v.enabled !== false) ? ": a version plays instead" : ""}
            </span>
          )}
          {weight !== 5 && <span className="badge badge-accent">Plays {weightLabel(weight).toLowerCase()}</span>}
          <LoudnessTag info={loudness?.(preroll)} />
        </div>
        {versions.length > 0 && (
          <div className="versions">
            <p className="small muted row">
              <Layers size={14} aria-hidden="true" /> {versions.length === 1 ? "1 version" : `${versions.length} versions`}
            </p>
            <ul className="version-list">
              {versions.map((v) => (
                <li key={v.id}>
                  <span className="version-name small">{v.version_label || videoName(v)}</span>
                  <span className="version-tags">
                    {v.enabled === false ? <span className="badge">Off</span> : off && <span className="badge badge-success">Plays</span>}
                    <LoudnessTag info={loudness?.(v)} />
                  </span>
                  <IconButton label={`Play ${videoName(v)}`} onClick={() => onPreview(v)}>
                    <Play size={16} aria-hidden="true" />
                  </IconButton>
                  <IconButton label={`Delete ${videoName(v)}`} onClick={() => onDelete(v)}>
                    <Trash2 size={16} aria-hidden="true" />
                  </IconButton>
                </li>
              ))}
            </ul>
          </div>
        )}
        {preroll.file_exists === false && <p className="field-error">The video file is missing from disk.</p>}
        <div className="video-actions">
          {onSelect ? (
            <label className="checkbox grow small">
              <input type="checkbox" checked={Boolean(selected)} onChange={onSelect} aria-label={`Select ${name}`} />
              <span aria-hidden="true">{formatSize(preroll.file_size) || "Select"}</span>
            </label>
          ) : (
            <span className="muted small grow">{formatSize(preroll.file_size)}</span>
          )}
          <IconButton label={`Edit ${name}`} onClick={onEdit}>
            <Pencil size={18} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Delete ${name}`} onClick={() => onDelete(preroll)}>
            <Trash2 size={18} aria-hidden="true" />
          </IconButton>
        </div>
      </div>
    </li>
  );
}
