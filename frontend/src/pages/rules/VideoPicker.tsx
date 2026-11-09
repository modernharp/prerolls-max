// Choose intro videos from the library: search, tick, and see the chosen
// ones in the order they'll play.
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search, X } from "lucide-react";
import { videoName } from "../../lib/format";
import type { Preroll } from "../../lib/types";
import { FieldShell } from "../../components/Field";
import { IconButton } from "../../components/Button";

interface Props {
  videos: Preroll[];
  value: number[];
  onChange: (ids: number[]) => void;
  ordered: boolean;
  error?: string;
}

export function VideoPicker({ videos, value, onChange, ordered, error }: Props) {
  const [q, setQ] = useState("");
  const byId = useMemo(() => new Map(videos.map((v) => [v.id, v])), [videos]);
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return videos.filter((v) => words.every((w) => videoName(v).toLowerCase().includes(w))).slice(0, 200);
  }, [videos, q]);
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  const move = (i: number, dir: -1 | 1) => {
    const next = [...value];
    const [id] = next.splice(i, 1);
    if (id === undefined) return;
    next.splice(i + dir, 0, id);
    onChange(next);
  };

  return (
    <FieldShell label="Intro videos" group error={error} help={ordered ? "They play in the order shown under Chosen." : "One or more is picked at random each time."}>
      {(ids) => (
        <div className="stack-sm" aria-describedby={ids.describedBy}>
          {value.length > 0 && (
            <ol className="picked-list">
              {value.map((id, i) => (
                <li key={id}>
                  <span className="grow">{byId.get(id) ? videoName(byId.get(id)!) : `A video that was deleted (${id})`}</span>
                  {ordered && (
                    <>
                      <IconButton label="Play earlier" disabled={i === 0} onClick={() => move(i, -1)}>
                        <ArrowUp size={16} aria-hidden="true" />
                      </IconButton>
                      <IconButton label="Play later" disabled={i === value.length - 1} onClick={() => move(i, 1)}>
                        <ArrowDown size={16} aria-hidden="true" />
                      </IconButton>
                    </>
                  )}
                  <IconButton label="Remove" onClick={() => toggle(id)}>
                    <X size={16} aria-hidden="true" />
                  </IconButton>
                </li>
              ))}
            </ol>
          )}
          <div className="field search-field">
            <label htmlFor={`${ids.id}-q`} className="visually-hidden">
              Search your videos
            </label>
            <Search size={18} className="search-icon" aria-hidden="true" />
            <input id={`${ids.id}-q`} className="input search-input" type="search" placeholder="Search your videos" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <ul className="pick-list">
            {shown.map((v) => (
              <li key={v.id}>
                <label className="checkbox">
                  <input type="checkbox" checked={value.includes(v.id)} onChange={() => toggle(v.id)} />
                  {videoName(v)}
                </label>
              </li>
            ))}
            {!shown.length && <li className="muted small">No videos match.</li>}
          </ul>
        </div>
      )}
    </FieldShell>
  );
}
