// "Only if…" for one playlist step: the rules, how they combine, and what
// plays otherwise. Plex can't tell what's about to play, so rules that need
// that are flagged: on Plex the Otherwise step plays.
import { Plus, Trash2 } from "lucide-react";
import * as RPopover from "@radix-ui/react-popover";
import { AUDIO_FORMATS, TRAILER_RATINGS, type Block, type Rule } from "../../../../lib/playlist";
import { SERVER_NAMES, pluginWorking, useCapabilities, type ServerType } from "../../../../lib/capabilities";
import { useMediaServers } from "../../../../lib/mediaServers";
import { Select } from "../../../../components/Select";
import { TextField } from "../../../../components/Field";
import { ToggleChips } from "../../../../components/Controls";
import { Button, IconButton } from "../../../../components/Button";
import { CapabilityBadge } from "../../../../components/CapabilityBadge";
import { RULE_KINDS, ruleKind, usesPlayback } from "./playlistText";
import { StepFields } from "./StepFields";

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

function newRule(kind: string): Rule {
  switch (kind) {
    case "media_type":
      return { kind, value: "movie" };
    case "time_window":
      return { kind, start: "18:00", end: "22:00" };
    case "server":
      return { kind, values: ["jellyfin", "emby"] };
    case "trailers_available":
      return { kind, source: "both", min: 1 };
    case "audio_format":
      return { kind, values: [], track: "default" };
    case "first_in_session":
      return { kind };
    default:
      return { kind, values: [] };
  }
}

const listText = (values?: string[]) => (values ?? []).join(", ");
const fromText = (text: string) => text.split(",").map((v) => v.trim()).filter(Boolean);

function RuleValue({ rule, onChange, id }: { rule: Rule; onChange: (r: Rule) => void; id: string }) {
  switch (rule.kind) {
    case "rating":
      return (
        <fieldset className="plain-fieldset">
          <legend className="visually-hidden">Age ratings</legend>
          <ToggleChips options={TRAILER_RATINGS.map((r) => ({ value: r, label: r }))} selected={rule.values ?? []} onChange={(values) => onChange({ ...rule, values })} />
        </fieldset>
      );
    case "audio_format":
      return (
        <fieldset className="plain-fieldset">
          <legend className="visually-hidden">Sound formats</legend>
          <ToggleChips options={AUDIO_FORMATS.map(([value, label]) => ({ value, label }))} selected={rule.values ?? []} onChange={(values) => onChange({ ...rule, values })} />
        </fieldset>
      );
    case "server":
      return <ServerChoice rule={rule} onChange={onChange} />;
    case "media_type":
      return (
        <Select
          id={id}
          label={<span className="visually-hidden">Movie or episode</span>}
          value={rule.value ?? "movie"}
          onChange={(value) => onChange({ ...rule, value })}
          options={[
            { value: "movie", label: "A movie" },
            { value: "episode", label: "A TV episode" },
          ]}
        />
      );
    case "time_window":
      return (
        <div className="stack-sm">
          <div className="input-row">
            <TextField label="From" type="time" value={rule.start ?? ""} onChange={(e) => onChange({ ...rule, start: e.target.value })} />
            <TextField label="Until" type="time" value={rule.end ?? ""} onChange={(e) => onChange({ ...rule, end: e.target.value })} />
          </div>
          <fieldset className="plain-fieldset">
            <legend className="field-help">On these days (none picked means every day)</legend>
            <ToggleChips
              options={WEEKDAYS.map((d) => ({ value: d, label: d.charAt(0).toUpperCase() + d.slice(1, 3) }))}
              selected={rule.days ?? []}
              onChange={(days) => onChange({ ...rule, days })}
            />
          </fieldset>
        </div>
      );
    case "first_in_session":
    case "trailers_available":
      return <span className="muted small">Nothing to fill in.</span>;
    default:
      return (
        <TextField
          key={rule.kind}
          id={id}
          label={<span className="visually-hidden">Values</span>}
          placeholder={rule.kind === "genre" ? "Horror, Thriller" : rule.kind === "file_name" ? "IMAX" : "Separate several with commas"}
          defaultValue={listText(rule.values)}
          onBlur={(e) => onChange({ ...rule, values: fromText(e.target.value) })}
        />
      );
  }
}

/** Any Plex, Jellyfin or Emby, or one server by name when there are several of its type. */
function ServerChoice({ rule, onChange }: { rule: Rule; onChange: (r: Rule) => void }) {
  const servers = useMediaServers();
  const list = servers.data ?? [];
  const options = (["plex", "jellyfin", "emby"] as ServerType[]).flatMap((t) => {
    const mine = list.filter((s) => s.type === t);
    const any = { value: t as string, label: mine.length > 1 ? `Any ${SERVER_NAMES[t]}` : SERVER_NAMES[t] };
    return mine.length > 1 ? [any, ...mine.map((s) => ({ value: `server:${s.id}`, label: s.name }))] : [any];
  });
  return (
    <fieldset className="plain-fieldset">
      <legend className="visually-hidden">Media servers</legend>
      <ToggleChips options={options} selected={rule.values ?? []} onChange={(values) => onChange({ ...rule, values })} />
      {list.filter((s) => s.type === "plex").length > 1 && (
        <p className="field-help">Plex servers all get one list, so a Plex server named here counts as every Plex server.</p>
      )}
    </fieldset>
  );
}

/** Which servers can check these rules. */
function ServerNotes({ rules }: { rules: Rule[] }) {
  const caps = useCapabilities();
  const playback = usesPlayback(rules);
  const feature = rules.map((r) => ruleKind(r.kind)?.feature).find(Boolean);
  if (!caps.data || !feature) return null;
  return (
    <span className="chips feature-badges">
      {caps.data.servers.map((s) =>
        s.type === "plex" && playback ? (
          <RPopover.Root key={s.type}>
            <RPopover.Trigger asChild>
              <button type="button" className="badge badge-warning" aria-label="Plex: plays the Otherwise step. Why?">
                Plex: plays the Otherwise step
              </button>
            </RPopover.Trigger>
            <RPopover.Portal>
              <RPopover.Content className="popover" sideOffset={6}>
                Plex picks intros before it knows which movie starts, so it can't check this. On Plex the Otherwise step plays
                (or nothing, if there isn't one).
              </RPopover.Content>
            </RPopover.Portal>
          </RPopover.Root>
        ) : (
          <CapabilityBadge key={s.type} server={s.type} info={s.features[feature]} plugin={pluginWorking(s)} />
        ),
      )}
    </span>
  );
}

interface Props {
  block: Block;
  onChange: (block: Block) => void;
  idPrefix: string;
}

export function ConditionEditor({ block, onChange, idPrefix }: Props) {
  const rules = block.condition?.rules ?? [];
  const setRules = (next: Rule[]) => onChange({ ...block, condition: { match: block.condition?.match ?? "all", rules: next } });
  const setRule = (i: number, rule: Rule) => setRules(rules.map((r, j) => (j === i ? rule : r)));
  const otherwise = block.otherwise;
  return (
    <div className="stack-sm">
      <div className="condition-box">
        <div className="row-between">
          <strong>Only if</strong>
          {rules.length > 1 && (
            <div className="toolbar-select">
              <Select
                label={<span className="visually-hidden">How the rules combine</span>}
                value={block.condition?.match ?? "all"}
                onChange={(match) => onChange({ ...block, condition: { rules, match: match as "all" | "any" } })}
                options={[
                  { value: "all", label: "All of these are true" },
                  { value: "any", label: "Any of these is true" },
                ]}
              />
            </div>
          )}
        </div>
        {rules.map((rule, i) => (
          <div key={`${idPrefix}-r${i}`} className="rule-row">
            <Select
              label={<span className="visually-hidden">Rule {i + 1}</span>}
              value={rule.kind}
              onChange={(kind) => setRule(i, newRule(kind))}
              options={RULE_KINDS.map((k) => ({ value: k.value, label: k.label }))}
            />
            <div className="rule-value">
              <RuleValue rule={rule} id={`${idPrefix}-v${i}`} onChange={(r) => setRule(i, r)} />
            </div>
            <label className="checkbox small">
              <input type="checkbox" checked={Boolean(rule.negate)} onChange={(e) => setRule(i, { ...rule, negate: e.target.checked || undefined })} />
              Not
              <span className="visually-hidden"> (turn rule {i + 1} around)</span>
            </label>
            <IconButton label={`Remove rule ${i + 1}`} onClick={() => setRules(rules.filter((_, j) => j !== i))}>
              <Trash2 size={18} aria-hidden="true" />
            </IconButton>
          </div>
        ))}
        <div>
          <Button size="sm" icon={<Plus size={16} aria-hidden="true" />} onClick={() => setRules([...rules, newRule("genre")])}>
            Add a rule
          </Button>
        </div>
        <ServerNotes rules={rules} />
      </div>
      <div className="otherwise-box">
        <strong>Otherwise</strong>
        <Select
          label={<span className="visually-hidden">What plays otherwise</span>}
          value={otherwise?.type ?? "none"}
          onChange={(type) => onChange({ ...block, otherwise: type === "none" ? undefined : { type, count: 1 } })}
          options={[
            { value: "none", label: "Play nothing in this spot" },
            { value: "random", label: "Random videos from a collection" },
            { value: "fixed", label: "Videos you choose" },
            { value: "nexup_trailers", label: "Movie trailers" },
          ]}
        />
        {otherwise && <StepFields block={otherwise} onChange={(o) => onChange({ ...block, otherwise: o })} idPrefix={`${idPrefix}-o`} />}
      </div>
    </div>
  );
}
