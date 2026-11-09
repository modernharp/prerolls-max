// Age ratings, one rating system at a time (US movies, US TV, UK...), with
// the kids-safe ones marked. Ratings chosen in other systems stay chosen.
import { useState } from "react";
import { X } from "lucide-react";
import type { RatingFamily } from "../../lib/rules";
import { Select } from "../../components/Select";
import { FieldShell } from "../../components/Field";

interface Props {
  families: RatingFamily[];
  value: string[];
  onChange: (next: string[]) => void;
  error?: string;
}

export function RatingPicker({ families, value, onChange, error }: Props) {
  const [familyId, setFamilyId] = useState(families[0]?.id ?? "");
  const family = families.find((f) => f.id === familyId) ?? families[0];
  const has = (r: string) => value.some((v) => v.toLowerCase() === r.toLowerCase());
  const toggle = (r: string) => onChange(has(r) ? value.filter((v) => v.toLowerCase() !== r.toLowerCase()) : [...value, r]);

  return (
    <FieldShell
      label="Age ratings"
      optional
      group
      error={error}
      help="Matches titles rated any of these. Pick a rating system, then tap ratings to choose them."
    >
      {(ids) => (
        <div className="stack-sm">
          <div className="toolbar-select">
            <Select
              label={<span className="visually-hidden">Rating system</span>}
              value={family?.id ?? ""}
              onChange={setFamilyId}
              options={families.map((f) => ({ value: f.id, label: f.name }))}
            />
          </div>
          {family && (
            <div className="chips" aria-describedby={ids.describedBy}>
              {family.ratings.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  className="chip"
                  aria-pressed={has(r.value)}
                  title={r.label}
                  onClick={() => toggle(r.value)}
                >
                  {r.value}
                  {r.kids_safe && <span className="chip-note">kids-safe</span>}
                </button>
              ))}
            </div>
          )}
          {value.length > 0 && (
            <div className="row small">
              <span className="muted">Chosen:</span>
              {value.map((r) => (
                <button key={r} type="button" className="badge badge-accent removable" onClick={() => toggle(r)} aria-label={`Remove ${r}`}>
                  {r} <X size={12} aria-hidden="true" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </FieldShell>
  );
}
