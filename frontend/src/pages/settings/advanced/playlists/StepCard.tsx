// One step of a playlist, with its sentence, settings and "only if".
import { ArrowDown, ArrowUp, Copy, Trash2 } from "lucide-react";
import type { Block } from "../../../../lib/playlist";
import { Select } from "../../../../components/Select";
import { SwitchRow } from "../../../../components/Controls";
import { IconButton } from "../../../../components/Button";
import { AlertCircle } from "lucide-react";
import { ConditionEditor } from "./ConditionEditor";
import { StepFields } from "./StepFields";
import { STEP_KINDS, describeCondition, describeStep, type Lookup } from "./playlistText";

interface Props {
  block: Block;
  index: number;
  total: number;
  errors: string[];
  lookup: Lookup;
  onChange: (block: Block) => void;
  onMove: (delta: number) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}

export function blankStep(type: string): Block {
  switch (type) {
    case "fixed":
      return { type, preroll_ids: [] };
    case "nexup_trailers":
      return { type, count: 2, source: "movies", mode: "random" };
    case "library_trailers":
      return { type, count: 2, mode: "random" };
    case "coming_soon_list":
      return { type, layout: "list" };
    case "separator":
      return { type, duration: 3 };
    default:
      return { type, count: 1 };
  }
}

export function StepCard({ block, index, total, errors, lookup, onChange, onMove, onDuplicate, onRemove }: Props) {
  const idPrefix = `step${index}`;
  const conditional = Boolean(block.condition);
  const condition = describeCondition(block);
  const known = STEP_KINDS.some((k) => k.value === block.type);
  return (
    <li className={`step-card ${errors.length ? "invalid" : ""}`} aria-labelledby={`${idPrefix}-title`}>
      <div className="step-head">
        <span className="step-num" aria-hidden="true" />
        <div className="grow">
          <h3 id={`${idPrefix}-title`} className="h4-like">
            <span className="visually-hidden">Step {index + 1}: </span>
            {describeStep(block, lookup)}
          </h3>
          {condition && <p className="muted small">{condition}.</p>}
        </div>
        <div className="step-tools">
          <IconButton label={`Move step ${index + 1} up`} disabled={index === 0} onClick={() => onMove(-1)}>
            <ArrowUp size={18} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Move step ${index + 1} down`} disabled={index === total - 1} onClick={() => onMove(1)}>
            <ArrowDown size={18} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Copy step ${index + 1}`} onClick={onDuplicate}>
            <Copy size={18} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Remove step ${index + 1}`} onClick={onRemove}>
            <Trash2 size={18} aria-hidden="true" />
          </IconButton>
        </div>
      </div>
      {known && (
        <Select
          id={`${idPrefix}-kind`}
          label="What plays"
          value={block.type}
          onChange={(type) => onChange({ ...blankStep(type), condition: block.condition, otherwise: block.otherwise })}
          options={STEP_KINDS.map((k) => ({ value: k.value, label: k.label }))}
        />
      )}
      <StepFields block={block} onChange={onChange} idPrefix={idPrefix} />
      <SwitchRow
        label="Only play this in some cases"
        description="For example, only before horror movies, or only in the evening."
        checked={conditional}
        onChange={(on) =>
          onChange(on ? { ...block, condition: { match: "all", rules: [{ kind: "genre", values: [] }] } } : { ...block, condition: undefined, otherwise: undefined })
        }
      />
      {conditional && <ConditionEditor block={block} onChange={onChange} idPrefix={idPrefix} />}
      {errors.length > 0 && (
        <div className="field-error" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>{errors.join(" ")}</span>
        </div>
      )}
    </li>
  );
}
