// Playlists (the server calls them sequences): their shape, checks before
// saving, and the cleanup that strips editor-only fields. Ported from the
// old interface's utils/sequenceValidator.js, with plain messages that name
// things instead of quoting ids.
import type { CategoryRef } from "./types";

export const BLOCK_TYPES = [
  "random", "fixed", "sequential", "nexup_trailers", "library_trailers", "coming_soon_list", "dynamic_preroll", "separator",
] as const;
export type BlockType = (typeof BLOCK_TYPES)[number];

export const TRAILER_RATINGS = ["G", "PG", "PG-13", "R", "NC-17", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "TV-PG", "TV-14", "TV-MA", "Unrated"];

export const AUDIO_FORMATS: [string, string][] = [
  ["ac3", "Dolby Digital"], ["eac3", "Dolby Digital Plus"], ["truehd", "Dolby TrueHD"],
  ["dts", "DTS / DTS-HD"], ["aac", "AAC"], ["flac", "FLAC"], ["pcm", "PCM"],
  ["mp3", "MP3"], ["opus", "Opus"], ["vorbis", "Vorbis"],
];

export interface Rule {
  kind: string;
  values?: string[];
  value?: string;
  start?: string;
  end?: string;
  days?: string[];
  negate?: boolean;
  track?: "default" | "any";
  source?: string;
  min?: number;
  pool?: string;
}

export interface Condition {
  match?: "all" | "any";
  rules: Rule[];
}

export interface Point {
  x: number;
  y: number;
}

export interface Block {
  /** Editor-only id; never saved. */
  id?: string;
  type: string;
  label?: string;
  category_id?: number;
  category_name?: string;
  count?: number;
  preroll_ids?: number[];
  source?: string;
  mode?: string;
  genres?: string[];
  match_playing?: boolean;
  match_playing_only?: boolean;
  ratings?: string[];
  restrict_ratings?: boolean;
  layout?: string;
  filename?: string;
  template?: string;
  theme?: string;
  duration?: number;
  condition?: Condition;
  otherwise?: Block;
  else_if?: boolean;
  flow_positions?: Record<string, Point>;
  [key: string]: unknown;
}

export interface SavedPlaylist {
  id: number;
  name: string;
  description: string | null;
  blocks: Block[];
  created_at?: string | null;
  updated_at?: string | null;
}

interface Named {
  id: number;
}

const isType = (value: string): value is BlockType => (BLOCK_TYPES as readonly string[]).includes(value);

function countProblem(raw: unknown, max: number, required: boolean, noun = ""): string | null {
  if (raw === undefined || raw === null || raw === "") return required ? "Say how many to play." : null;
  const count = Number.parseInt(String(raw), 10);
  if (Number.isNaN(count) || count < 1) return `Play at least 1${noun ? ` ${noun}` : ""}.`;
  if (count > max) return `Play ${max}${noun ? ` ${noun}s` : ""} or fewer.`;
  return null;
}

/** Problems with one step, in plain words. Empty when it's fine. */
export function validateBlock(block: Block | null | undefined, categories: CategoryRef[] = [], prerolls: Named[] = []): string[] {
  const errors: string[] = [];
  if (!block || typeof block !== "object") return ["This step is empty."];
  if (!block.type) return ["Pick what this step plays."];
  const type = String(block.type).toLowerCase();
  if (!isType(type)) return ["Prerolls Max doesn't know this kind of step. Remove it and add it again."];

  if (type === "random" || type === "sequential") {
    if (!block.category_id && !(type === "sequential" && block.category_name)) errors.push("Pick a collection.");
    else if (block.category_id && !categories.some((c) => c.id === block.category_id)) {
      errors.push("The collection this step uses doesn't exist anymore. Pick another.");
    }
    const problem = countProblem(block.count, 10, type === "random");
    if (problem) errors.push(problem);
  }

  if (type === "fixed") {
    const ids = block.preroll_ids;
    if (!Array.isArray(ids) || !ids.length) errors.push("Pick at least one video.");
    else {
      const missing = ids.filter((id) => !prerolls.some((p) => p.id === id)).length;
      if (missing) errors.push(missing === 1 ? "One of the videos isn't in your library anymore." : `${missing} of the videos aren't in your library anymore.`);
    }
  }

  if (type === "nexup_trailers") {
    if (block.source && !["movies", "tv", "both"].includes(block.source)) errors.push("Pick movies, TV shows or both.");
    const problem = countProblem(block.count, 20, false, "trailer");
    if (problem) errors.push(problem);
  }

  if (type === "coming_soon_list" && block.layout && !["grid", "list"].includes(block.layout)) {
    errors.push("Pick the grid or the list layout.");
  }

  if (type === "separator") {
    const duration = Number(block.duration ?? 3);
    if (!Number.isFinite(duration) || duration < 1) errors.push("A pause lasts at least 1 second.");
    else if (duration > 60) errors.push("A pause lasts 60 seconds at most.");
  }

  if (type === "dynamic_preroll" && !block.filename && !(block.template && block.theme)) {
    errors.push("Pick a video from the video maker.");
  }

  if ((type === "nexup_trailers" || type === "library_trailers") && block.ratings !== undefined) {
    if (!Array.isArray(block.ratings) || block.ratings.some((r) => !TRAILER_RATINGS.includes(r))) errors.push("Pick age ratings from the list.");
  }

  if (block.otherwise && typeof block.otherwise === "object" && !block.otherwise.otherwise) {
    errors.push(...validateBlock(block.otherwise, categories, prerolls).map((e) => `Otherwise: ${e}`));
  }

  for (const rule of block.condition?.rules ?? []) {
    errors.push(...validateRule(rule));
  }
  return errors;
}

/** Problems with one "only if" rule. */
export function validateRule(rule: Rule): string[] {
  const values = (rule.values ?? []).map((v) => String(v).trim()).filter(Boolean);
  switch (rule?.kind) {
    case "audio_format":
      if (!values.length || values.some((v) => !AUDIO_FORMATS.some(([key]) => key === v))) return ["Pick at least one sound format."];
      if (rule.track !== undefined && !["default", "any"].includes(rule.track)) return ["Pick which audio track to check."];
      return [];
    case "server":
      return values.length && values.every((v) => ["plex", "jellyfin", "emby"].includes(v) || /^server:\d+$/.test(v))
        ? []
        : ["Pick at least one media server."];
    case "tag":
      return values.length ? [] : ["Add at least one tag."];
    case "file_name":
      return values.length ? [] : ["Add the text the file name should contain."];
    case "genre":
      return values.length ? [] : ["Add at least one genre."];
    case "rating":
      return values.length ? [] : ["Pick at least one age rating."];
    case "user":
      return values.length ? [] : ["Add at least one person's user name."];
    case "library":
      return values.length ? [] : ["Add at least one library name."];
    case "media_type":
      return rule.value === "movie" || rule.value === "episode" ? [] : ["Pick movies or TV episodes."];
    case "time_window":
      return /^\d{1,2}:\d{2}$/.test(rule.start ?? "") && /^\d{1,2}:\d{2}$/.test(rule.end ?? "") ? [] : ["Enter both times, like 18:00 and 22:00."];
    default:
      return [];
  }
}

export function validateSequence(sequence: unknown, categories: CategoryRef[] = [], prerolls: Named[] = []): { valid: boolean; errors: string[] } {
  if (!sequence) return { valid: false, errors: ["Add at least one step."] };
  if (!Array.isArray(sequence)) return { valid: false, errors: ["This playlist can't be read."] };
  if (!sequence.length) return { valid: false, errors: ["Add at least one step."] };
  const errors: string[] = [];
  sequence.forEach((block: Block, index) => {
    const problems = validateBlock(block, categories, prerolls);
    if (problems.length) errors.push(`Step ${index + 1}: ${problems.join(" ")}`);
  });
  return { valid: errors.length === 0, errors };
}

// The fields a block of each type is saved with.
function sanitizeBlockFields(block: Block): Block {
  const out: Block = { type: block.type, ...(block.label && block.label.trim() ? { label: block.label.trim() } : {}) };
  if (block.type === "random" || block.type === "sequential") {
    out.category_id = block.category_id;
    out.count = block.count || 1;
  } else if (block.type === "fixed") {
    out.preroll_ids = block.preroll_ids || [];
  } else if (block.type === "nexup_trailers") {
    out.source = block.source || "both";
    out.count = block.count || 2;
    out.mode = block.mode || "random";
  } else if (block.type === "library_trailers") {
    out.count = block.count || 2;
    out.mode = block.mode || "random";
    out.genres = Array.isArray(block.genres) ? block.genres : [];
    out.match_playing = Boolean(block.match_playing);
  } else if (block.type === "coming_soon_list") {
    out.layout = block.layout || "grid";
  } else if (block.type === "dynamic_preroll") {
    out.filename = block.filename;
  } else if (block.type === "separator") {
    out.duration = block.duration || 3;
  }
  if (block.type === "nexup_trailers" || block.type === "library_trailers") {
    if (block.ratings !== undefined) out.ratings = block.ratings;
    if (block.restrict_ratings !== undefined) out.restrict_ratings = block.restrict_ratings;
    if (block.match_playing !== undefined) out.match_playing = Boolean(block.match_playing);
    if (block.match_playing_only !== undefined) out.match_playing_only = Boolean(block.match_playing_only);
  }
  return out;
}

/** Removes editor-only fields (ids, labels on alternatives, half-built conditions). */
export function sanitizeSequence(sequence: Block[]): Block[] {
  if (!Array.isArray(sequence)) return [];
  return sequence.map((block) => {
    const out = sanitizeBlockFields(block);
    const positions = Object.entries(block.flow_positions || {}).filter(
      ([key, point]) => /^(simple|advanced)_(b|if|o)$/.test(key) && Number.isFinite(point?.x) && Number.isFinite(point?.y),
    );
    if (positions.length) out.flow_positions = Object.fromEntries(positions.map(([key, p]) => [key, { x: p.x, y: p.y }]));
    if (block.condition && Array.isArray(block.condition.rules) && block.condition.rules.length) {
      out.condition = block.condition;
      if (block.otherwise && block.otherwise.type) {
        const { label: _label, ...otherwise } = sanitizeBlockFields(block.otherwise);
        out.otherwise = otherwise;
      }
    }
    if (block.else_if === true) out.else_if = true;
    return out;
  });
}

export function parseSequence(json: unknown): Block[] | null {
  if (!json) return [];
  if (Array.isArray(json)) return json as Block[];
  try {
    const parsed: unknown = JSON.parse(String(json));
    return Array.isArray(parsed) ? (parsed as Block[]) : null;
  } catch {
    return null;
  }
}

export function stringifySequence(sequence: Block[]): string {
  return JSON.stringify(sanitizeSequence(sequence));
}

let nextId = 0;
export function cloneSequenceWithIds(sequence: Block[]): Block[] {
  if (!Array.isArray(sequence)) return [];
  return sequence.map((block) => ({ ...block, id: `step-${Date.now().toString(36)}-${(nextId += 1)}` }));
}

/** Does the editor hold anything that isn't saved yet? */
export function sequenceHasUnsavedChanges(
  blocks: Block[],
  name: string,
  description: string,
  saved: Pick<SavedPlaylist, "name" | "description" | "blocks"> | null,
): boolean {
  const currentName = (name || "").trim();
  const currentDescription = (description || "").trim();
  if (!saved) return (Array.isArray(blocks) && blocks.length > 0) || currentName.length > 0 || currentDescription.length > 0;
  return (
    stringifySequence(blocks) !== stringifySequence(saved.blocks || []) ||
    currentName !== (saved.name || "").trim() ||
    currentDescription !== (saved.description || "").trim()
  );
}

/** Imported .nexseq blocks carry match notes (_unmatched, _missing_prerolls); drop them before saving. */
export function withoutImportNotes(blocks: Block[]): Block[] {
  const strip = (b: Block): Block => {
    const out: Block = { type: b.type };
    for (const [k, v] of Object.entries(b)) if (!k.startsWith("_")) out[k] = v;
    if (b.otherwise) out.otherwise = strip(b.otherwise);
    return out;
  };
  return blocks.map(strip);
}
