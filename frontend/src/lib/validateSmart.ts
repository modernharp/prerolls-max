// Checks for the smart-feature forms (rules, Playback settings, weights,
// cooldowns), with the same limits and messages as the server
// (app/backend/routers/rules.py, smart_settings.py, automation.py).
import { z } from "zod";
import { cleanName, type Check } from "./validate";
import type { MediaType, PlayOrder, Rule, RuleIn } from "./rules";

const ok = <T,>(value: T): Check<T> => ({ ok: true, value });
const fail = (message: string): Check<never> => ({ ok: false, message });

/** "Horror, Sci-Fi\nDrama" -> ["Horror", "Sci-Fi", "Drama"], without repeats. */
export function splitList(text: string): string[] {
  const out: string[] = [];
  for (const part of (text ?? "").split(/[,\n]/)) {
    const item = part.trim().replace(/\s+/g, " ");
    if (item && !out.some((o) => o.toLowerCase() === item.toLowerCase())) out.push(item);
  }
  return out;
}

export const joinList = (items: readonly string[] | null | undefined) => (items ?? []).join(", ");

/** A whole number from a text box, between min and max. */
export function checkWhole(text: string, min: number, max: number, message: string): Check<number> {
  const raw = String(text ?? "").trim();
  if (!/^-?\d+$/.test(raw)) return fail(message);
  const n = Number(raw);
  return n < min || n > max ? fail(message) : ok(n);
}

/** Any number (decimals allowed, comma or dot), between min and max. */
export function checkNumber(text: string, min: number, max: number, message: string): Check<number> {
  const raw = String(text ?? "").trim().replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return fail(message);
  const n = Number(raw);
  return n < min || n > max ? fail(message) : ok(n);
}

export const MESSAGES = {
  year: "Use a year between 1880 and 2200.",
  yearOrder: "The last year must be the same as or after the first year.",
  firstEpisode: "\"First episode only\" needs the rule to cover episodes.",
  source: "Choose a collection or some intro videos to play.",
  collection: "Choose a collection.",
  videos: "Choose at least one intro video.",
  count: "Play between 1 and 20 intros, or leave it empty.",
  cooldown: "Use 0 to 720 hours (30 days).",
  binge: "Use a whole number of hours from 1 to 48.",
  retention: "Keep history for 1 to 3650 days.",
  target: "Use a target from -31 to -10 LUFS. -23 is how TV and films are mixed.",
  tolerance: "Use 0.5 to 6 LU.",
  tag: "Each tag needs 1 to 60 characters.",
  tags: "Use 30 tags or fewer.",
  rating: "Use age ratings like G, PG or TV-Y7.",
  weight: "Use a number from 1 (rarely) to 10 (often).",
} as const;

export const DECADES = ["1920s", "1930s", "1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"];

/** "1980s" or "1985" or "80s" -> "1980s"; null when it isn't a decade. */
export function cleanDecade(text: string): string | null {
  const raw = (text ?? "").trim().toLowerCase().replace(/'/g, "");
  let m = /^(\d{4})s?$/.exec(raw);
  if (m) return `${Math.floor(Number(m[1]) / 10) * 10}s`;
  m = /^(\d)0s$/.exec(raw);
  if (m) return `19${m[1]}0s`;
  return null;
}

export function checkTags(text: string): Check<string[]> {
  const tags = splitList(text);
  if (tags.some((t) => t.length > 60)) return fail(MESSAGES.tag);
  if (tags.length > 30) return fail(MESSAGES.tags);
  return ok(tags);
}

// ---------------------------------------------------------------------------
// How often (weights 1-10)
// ---------------------------------------------------------------------------

export function weightLabel(weight: number): string {
  if (weight <= 2) return "Rarely";
  if (weight <= 4) return "Less often";
  if (weight === 5) return "Normal";
  if (weight <= 7) return "More often";
  return "Often";
}

// ---------------------------------------------------------------------------
// Rule form
// ---------------------------------------------------------------------------

export interface RuleDraft {
  name: string;
  enabled: boolean;
  genres: string;
  ratings: string[];
  kids_safe: boolean;
  decades: string[];
  year_from: string;
  year_to: string;
  libraries: string;
  users: string;
  media_type: MediaType;
  first_episode_only: boolean;
  source: "collection" | "videos";
  collection_id: string;
  preroll_ids: number[];
  count: string;
  order: PlayOrder;
  cooldown_hours: string;
}

export const EMPTY_RULE: RuleDraft = {
  name: "",
  enabled: true,
  genres: "",
  ratings: [],
  kids_safe: false,
  decades: [],
  year_from: "",
  year_to: "",
  libraries: "",
  users: "",
  media_type: "any",
  first_episode_only: false,
  source: "collection",
  collection_id: "",
  preroll_ids: [],
  count: "",
  order: "random",
  cooldown_hours: "0",
};

export function ruleToDraft(rule: Rule): RuleDraft {
  const w = rule.when;
  const p = rule.play;
  return {
    name: rule.name,
    enabled: rule.enabled,
    genres: joinList(w.genres),
    ratings: [...w.ratings],
    kids_safe: w.kids_safe,
    decades: [...w.decades],
    year_from: w.year_from ? String(w.year_from) : "",
    year_to: w.year_to ? String(w.year_to) : "",
    libraries: joinList(w.libraries),
    users: joinList(w.users),
    media_type: w.media_type,
    first_episode_only: w.first_episode_only,
    source: p.preroll_ids.length ? "videos" : "collection",
    collection_id: p.collection_id ? String(p.collection_id) : "",
    preroll_ids: [...p.preroll_ids],
    count: p.count ? String(p.count) : "",
    order: p.order,
    cooldown_hours: String(p.cooldown_hours ?? 0),
  };
}

const optionalYear = (text: string): Check<number | null> => (text.trim() ? checkWhole(text, 1880, 2200, MESSAGES.year) : ok(null));

/** Field name -> message for everything wrong with the draft. Empty when it can be saved. */
export function ruleProblems(d: RuleDraft): Partial<Record<keyof RuleDraft, string>> {
  const out: Partial<Record<keyof RuleDraft, string>> = {};
  const name = cleanName(d.name, { what: "rule name" });
  if (!name.ok) out.name = name.message;
  const from = optionalYear(d.year_from);
  const to = optionalYear(d.year_to);
  if (!from.ok) out.year_from = from.message;
  if (!to.ok) out.year_to = to.message;
  if (from.ok && to.ok && from.value && to.value && to.value < from.value) out.year_to = MESSAGES.yearOrder;
  if (d.first_episode_only && d.media_type === "movie") out.first_episode_only = MESSAGES.firstEpisode;
  if (d.source === "collection" && !d.collection_id) out.collection_id = MESSAGES.collection;
  if (d.source === "videos" && !d.preroll_ids.length) out.preroll_ids = MESSAGES.videos;
  if (d.count.trim()) {
    const count = checkWhole(d.count, 1, 20, MESSAGES.count);
    if (!count.ok) out.count = count.message;
  }
  const cooldown = checkWhole(d.cooldown_hours || "0", 0, 720, MESSAGES.cooldown);
  if (!cooldown.ok) out.cooldown_hours = cooldown.message;
  for (const field of ["genres", "libraries", "users"] as const) {
    if (splitList(d[field]).some((v) => v.length > 100)) out[field] = "Keep each one to 100 characters or fewer.";
  }
  return out;
}

/** The request body for POST/PUT /api/rules. Call ruleProblems first. */
export function draftToRuleIn(d: RuleDraft): RuleIn {
  const year = (text: string) => (text.trim() ? Number(text.trim()) : null);
  return {
    name: d.name.split(/\s+/).filter(Boolean).join(" "),
    enabled: d.enabled,
    when: {
      genres: splitList(d.genres),
      ratings: d.ratings,
      kids_safe: d.kids_safe,
      decades: d.decades,
      year_from: year(d.year_from),
      year_to: year(d.year_to),
      libraries: splitList(d.libraries),
      users: splitList(d.users),
      media_type: d.media_type,
      first_episode_only: d.media_type !== "movie" && d.first_episode_only,
    },
    play: {
      collection_id: d.source === "collection" && d.collection_id ? Number(d.collection_id) : null,
      preroll_ids: d.source === "videos" ? d.preroll_ids : [],
      count: d.count.trim() ? Number(d.count.trim()) : null,
      order: d.order,
      cooldown_hours: d.order === "random" ? Number(d.cooldown_hours || 0) : 0,
    },
  };
}

/** For React Hook Form: every ruleProblems message on its field. */
export const ruleSchema = z.custom<RuleDraft>((v) => typeof v === "object" && v !== null).superRefine((draft, ctx) => {
  for (const [field, message] of Object.entries(ruleProblems(draft))) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: [field], message });
  }
});

// ---------------------------------------------------------------------------
// Playback settings form
// ---------------------------------------------------------------------------

function zCheck<T>(check: (text: string) => Check<T>) {
  return z.string().transform((value, ctx) => {
    const result = check(value);
    if (!result.ok) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: result.message });
      return z.NEVER;
    }
    return result.value;
  });
}

export const playbackSchema = z.object({
  binge_window_hours: zCheck((v) => checkWhole(v, 1, 48, MESSAGES.binge)),
  kids_safe_ratings: z.array(z.string().min(1).max(20, MESSAGES.rating)),
  unrated_is_kids_safe: z.boolean(),
  honor_no_intro_tags: z.boolean(),
  no_intro_tags: zCheck(checkTags),
  history_enabled: z.boolean(),
  history_retention_days: zCheck((v) => checkWhole(v, 1, 3650, MESSAGES.retention)),
  loudness_target_lufs: zCheck((v) => checkNumber(v, -31, -10, MESSAGES.target)),
  loudness_tolerance_lu: zCheck((v) => checkNumber(v, 0.5, 6, MESSAGES.tolerance)),
  watch_sessions: z.boolean(),
  links_allow_home_network: z.boolean(),
});
export type PlaybackInput = z.input<typeof playbackSchema>;
export type PlaybackOutput = z.output<typeof playbackSchema>;
