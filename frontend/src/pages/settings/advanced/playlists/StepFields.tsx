// The settings of one playlist step: which collection, which videos, how many.
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useCategories, usePrerolls } from "../../../../lib/queries";
import { videoName } from "../../../../lib/format";
import { TRAILER_RATINGS, type Block } from "../../../../lib/playlist";
import { Select } from "../../../../components/Select";
import { FieldShell, TextField } from "../../../../components/Field";
import { SwitchRow, ToggleChips } from "../../../../components/Controls";
import { IconButton } from "../../../../components/Button";

interface Props {
  block: Block;
  onChange: (block: Block) => void;
  idPrefix: string;
}

function CountField({ block, onChange, max, label, idPrefix }: Props & { max: number; label: string }) {
  return (
    <TextField
      id={`${idPrefix}-count`}
      label={label}
      type="number"
      inputMode="numeric"
      min={1}
      max={max}
      value={block.count ?? ""}
      onChange={(e) => onChange({ ...block, count: e.target.value === "" ? undefined : Number(e.target.value) })}
    />
  );
}

function CollectionField({ block, onChange, idPrefix }: Props) {
  const categories = useCategories();
  const prerolls = usePrerolls();
  const options = (categories.data ?? []).map((c) => {
    const n = (prerolls.data ?? []).filter((p) => p.categories.some((pc) => pc.id === c.id)).length;
    return { value: String(c.id), label: `${c.name} (${n} ${n === 1 ? "video" : "videos"})` };
  });
  return (
    <Select
      id={`${idPrefix}-collection`}
      label="Collection"
      value={block.category_id ? String(block.category_id) : ""}
      onChange={(v) => onChange({ ...block, category_id: Number(v) })}
      options={options}
      placeholder={options.length ? "Choose a collection" : "No collections yet"}
    />
  );
}

function VideosField({ block, onChange, idPrefix }: Props) {
  const prerolls = usePrerolls();
  const [pick, setPick] = useState("");
  const chosen = block.preroll_ids ?? [];
  const nameOf = (id: number) => {
    const p = prerolls.data?.find((v) => v.id === id);
    return p ? videoName(p) : "A video that isn't in your library anymore";
  };
  const options = (prerolls.data ?? []).filter((p) => !chosen.includes(p.id)).map((p) => ({ value: String(p.id), label: videoName(p) }));
  return (
    <FieldShell label="Videos" group>
      {() => (
        <div className="stack-sm">
          {chosen.length > 0 && (
            <ol className="plain-list">
              {chosen.map((id, i) => (
                <li key={`${id}-${i}`} className="row-between">
                  <span>
                    {i + 1}. {nameOf(id)}
                  </span>
                  <IconButton label={`Remove ${nameOf(id)}`} onClick={() => onChange({ ...block, preroll_ids: chosen.filter((_, j) => j !== i) })}>
                    <Trash2 size={18} aria-hidden="true" />
                  </IconButton>
                </li>
              ))}
            </ol>
          )}
          <Select
            id={`${idPrefix}-add-video`}
            label={<span className="visually-hidden">Add a video</span>}
            value={pick}
            placeholder={options.length ? "Add a video…" : "No more videos to add"}
            options={options}
            onChange={(v) => {
              setPick("");
              onChange({ ...block, preroll_ids: [...chosen, Number(v)] });
            }}
          />
        </div>
      )}
    </FieldShell>
  );
}

function TrailerFields({ block, onChange, idPrefix }: Props) {
  const restrict = Boolean(block.restrict_ratings || block.ratings?.length);
  // "Trailers for movies you have" has no movies-or-TV choice.
  const upcoming = block.type === "nexup_trailers";
  return (
    <>
      <CountField block={block} onChange={onChange} idPrefix={idPrefix} max={20} label="How many trailers" />
      {upcoming && (
        <Select
          id={`${idPrefix}-source`}
          label="Trailers for"
          value={block.source ?? "both"}
          onChange={(source) => onChange({ ...block, source })}
          options={[
            { value: "movies", label: "Upcoming movies" },
            { value: "tv", label: "Upcoming TV shows" },
            { value: "both", label: "Both" },
          ]}
        />
      )}
      <div className="stack-sm span-all">
        <SwitchRow
          label="Only certain age ratings"
          description="For example, only G and PG before family films."
          checked={restrict}
          onChange={(on) => onChange({ ...block, restrict_ratings: on || undefined, ratings: on ? block.ratings ?? ["G", "PG"] : undefined })}
        />
        {restrict && (
          <fieldset className="plain-fieldset">
            <legend className="visually-hidden">Age ratings</legend>
            <ToggleChips options={TRAILER_RATINGS.map((r) => ({ value: r, label: r }))} selected={block.ratings ?? []} onChange={(ratings) => onChange({ ...block, ratings })} />
          </fieldset>
        )}
      </div>
    </>
  );
}

export function StepFields(props: Props) {
  const { block, onChange, idPrefix } = props;
  switch (block.type) {
    case "random":
      return (
        <div className="step-body">
          <CollectionField {...props} />
          <CountField {...props} max={10} label="How many videos" />
        </div>
      );
    case "sequential":
      return (
        <div className="step-body">
          <CollectionField {...props} />
          <CountField {...props} max={10} label="How many videos" />
        </div>
      );
    case "fixed":
      return <VideosField {...props} />;
    case "nexup_trailers":
    case "library_trailers":
      return (
        <div className="step-body">
          <TrailerFields {...props} />
        </div>
      );
    case "coming_soon_list":
      return (
        <div className="step-body">
          <Select
            id={`${idPrefix}-layout`}
            label="Which look"
            value={block.layout === "grid" ? "grid" : "list"}
            onChange={(layout) => onChange({ ...block, layout })}
            options={[
              { value: "list", label: "A list of titles" },
              { value: "grid", label: "Posters" },
            ]}
            help="Make it first, under Coming soon video on the Movie trailers page."
          />
        </div>
      );
    case "separator":
      return (
        <div className="step-body">
          <TextField
            id={`${idPrefix}-pause`}
            label="Seconds"
            type="number"
            min={1}
            max={60}
            value={block.duration ?? 3}
            onChange={(e) => onChange({ ...block, duration: e.target.value === "" ? undefined : Number(e.target.value) })}
          />
        </div>
      );
    default:
      return <p className="muted small">This kind of step was made elsewhere. It's kept as it is when you save.</p>;
  }
}
