// What you can do with the videos you ticked on Your videos.
import { Combine, MonitorCheck, Volume2, AudioLines } from "lucide-react";
import { plural } from "../../../lib/format";
import { Button } from "../../../components/Button";

interface Props {
  count: number;
  checking: boolean;
  onCheck: () => void;
  onEvenOut: () => void;
  onVersions: () => void;
  onCombine: () => void;
  onClear: () => void;
}

export function SelectionBar({ count, checking, onCheck, onEvenOut, onVersions, onCombine, onClear }: Props) {
  if (!count) return null;
  return (
    <div className="selection-bar media-bar" role="region" aria-label="Selected videos">
      <span className="grow">
        <strong>{plural(count, "video")}</strong> selected
      </span>
      <div className="media-bar-actions">
        <Button size="sm" icon={<AudioLines size={16} aria-hidden="true" />} loading={checking} onClick={onCheck}>
          Check loudness
        </Button>
        <Button size="sm" icon={<Volume2 size={16} aria-hidden="true" />} onClick={onEvenOut}>
          Even out loudness
        </Button>
        <Button size="sm" icon={<MonitorCheck size={16} aria-hidden="true" />} onClick={onVersions}>
          Make TV-friendly version
        </Button>
        <Button size="sm" icon={<Combine size={16} aria-hidden="true" />} onClick={onCombine} disabled={count < 2} title={count < 2 ? "Select at least two" : undefined}>
          Combine into one
        </Button>
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}
