import { useState } from "react";
import { CheckCircle2, ExternalLink, Film, Play } from "lucide-react";
import { formatDuration } from "../../../lib/format";
import { attribution, versionsText, watchLabel, type CommunityItem } from "./useCommunity";

interface Props {
  item: CommunityItem;
  sourceName: string;
  selected: boolean;
  onToggle: () => void;
  onPreview: () => void;
}

export function CommunityItemCard({ item, sourceName, selected, onToggle, onPreview }: Props) {
  const [broken, setBroken] = useState(false);
  const checkboxId = `pick-${item.id.replace(/[^a-z0-9]/gi, "-")}`;
  const canPreview = Boolean(item.preview_url || item.embed_url);
  const versions = versionsText(item);
  const credit = attribution(item, sourceName);
  return (
    <li className={`video-card ${selected ? "selected" : ""}`}>
      <div className="thumb-button" data-static={!canPreview || undefined}>
        {item.thumbnail_url && !broken ? (
          <img className="thumb" src={item.thumbnail_url} alt="" loading="lazy" onError={() => setBroken(true)} />
        ) : (
          <div className="thumb thumb-empty" aria-hidden="true">
            <Film size={32} />
          </div>
        )}
        {item.duration_seconds ? <span className="thumb-length">{formatDuration(item.duration_seconds)}</span> : null}
        {canPreview && (
          <button type="button" className="thumb-overlay" onClick={onPreview} aria-label={`Watch a preview of ${item.title}`}>
            <span className="thumb-play" aria-hidden="true">
              <Play size={28} />
            </span>
          </button>
        )}
      </div>
      <div className="video-body">
        <h3 className="video-name" title={item.title}>
          {item.title}
        </h3>
        <p className="muted small credit">
          {item.creator?.url && item.creator.name && credit.includes(item.creator.name) ? (
            <>
              {credit.slice(0, credit.indexOf(item.creator.name))}
              <a href={item.creator.url} target="_blank" rel="noreferrer noopener">
                {item.creator.name}
              </a>
              {credit.slice(credit.indexOf(item.creator.name) + item.creator.name.length)}
            </>
          ) : (
            credit
          )}
        </p>
        {versions && <p className="muted small credit">{versions}</p>}
        <div className="video-actions">
          {item.in_library ? (
            <span className="badge badge-success" title={`Saved as "${item.in_library.name}"`}>
              <CheckCircle2 size={14} aria-hidden="true" /> In your library
            </span>
          ) : item.downloadable ? (
            <label className="checkbox grow" htmlFor={checkboxId}>
              <input id={checkboxId} type="checkbox" checked={selected} onChange={onToggle} />
              Select
            </label>
          ) : (
            <a className="btn btn-sm" href={item.watch_url || item.page_url} target="_blank" rel="noreferrer noopener">
              <ExternalLink size={16} aria-hidden="true" />
              {watchLabel(item)}
            </a>
          )}
        </div>
      </div>
    </li>
  );
}
