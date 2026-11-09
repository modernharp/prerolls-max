// Playlist steps and "only if" rules described in plain sentences.
import { listWords } from "../../../../lib/scheduleText";
import { formatTime } from "../../../../lib/format";
import { AUDIO_FORMATS, type Block, type Rule } from "../../../../lib/playlist";
import type { Feature } from "../../../../lib/capabilities";
import { SERVER_LABELS } from "../../../../lib/mediaServers";

export interface Lookup {
  collection: (id?: number) => string | undefined;
  video: (id: number) => string | undefined;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
/** "Horror or Thriller": a rule is met by any of its values. */
const anyOf = (words: string[]) => (words.length <= 1 ? words[0] ?? "" : `${words.slice(0, -1).join(", ")} or ${words[words.length - 1]}`);

export const STEP_KINDS: { value: string; label: string; desc: string }[] = [
  { value: "random", label: "Random videos from a collection", desc: "A different pick each time." },
  { value: "fixed", label: "Videos you choose", desc: "The same videos every time, in the order you add them." },
  { value: "sequential", label: "A collection, in order", desc: "Videos from a collection, one after another." },
  { value: "nexup_trailers", label: "Movie trailers", desc: "Trailers for upcoming movies, from the Movie trailers page." },
  { value: "library_trailers", label: "Trailers for movies you have", desc: "Trailers for movies already in your library, from the Movie trailers page." },
  { value: "coming_soon_list", label: "Coming soon video", desc: "The video listing what's coming soon, made on the Movie trailers page." },
  { value: "separator", label: "A short pause", desc: "A few seconds of black between videos." },
];

export function describeStep(block: Block, lookup: Lookup): string {
  const count = Number(block.count) || 1;
  switch (block.type) {
    case "random": {
      const name = lookup.collection(block.category_id);
      return name ? `${plural(count, "random video")} from ${name}` : `${plural(count, "random video")} from a collection`;
    }
    case "sequential": {
      const name = lookup.collection(block.category_id) ?? block.category_name;
      return name ? `${plural(count, "video")} from ${name}, in order` : "Videos from a collection, in order";
    }
    case "fixed": {
      const names = (block.preroll_ids ?? []).map((id) => lookup.video(id) ?? "a video that's gone");
      return names.length ? listWords(names) : "Videos you choose";
    }
    case "nexup_trailers": {
      const what = block.source === "tv" ? "TV show trailer" : block.source === "movies" ? "movie trailer" : "trailer";
      const ratings = block.ratings?.length ? ` rated ${listWords(block.ratings)}` : "";
      return `${plural(Number(block.count) || 2, what)}${ratings}`;
    }
    case "library_trailers":
      return `${plural(Number(block.count) || 2, "trailer")} for movies in your library`;
    case "coming_soon_list":
      return "A coming soon list of upcoming movies";
    case "dynamic_preroll":
      return "A video from the video maker";
    case "separator":
      return `A ${Number(block.duration) || 3}-second pause`;
    default:
      return "A step this page can't show";
  }
}

export interface RuleKind {
  value: string;
  label: string;
  /** Needs to know what's about to play: only Jellyfin and Emby can tell. */
  playback: boolean;
  feature?: Feature;
}

export const RULE_KINDS: RuleKind[] = [
  { value: "genre", label: "The genre is", playback: true, feature: "genre_rules" },
  { value: "rating", label: "The age rating is", playback: true, feature: "rating_rules" },
  { value: "time_window", label: "The time is between", playback: false, feature: "time_of_day" },
  { value: "media_type", label: "What's playing is", playback: true, feature: "episodes" },
  { value: "user", label: "The person watching is", playback: true, feature: "per_user" },
  { value: "library", label: "The library is", playback: true, feature: "per_library" },
  { value: "first_in_session", label: "It's the first episode after a break", playback: true, feature: "first_episode_only" },
  { value: "tag", label: "It has the tag", playback: true, feature: "genre_rules" },
  { value: "file_name", label: "The file name contains", playback: true, feature: "genre_rules" },
  { value: "audio_format", label: "The sound format is", playback: true, feature: "genre_rules" },
  { value: "server", label: "The media server is", playback: false },
  { value: "trailers_available", label: "Movie trailers are ready", playback: false, feature: "trailers" },
];

export const ruleKind = (kind: string) => RULE_KINDS.find((k) => k.value === kind);
export const usesPlayback = (rules: Rule[]) => rules.some((r) => ruleKind(r.kind)?.playback);

const SERVERS: Record<string, string> = { plex: "Plex", jellyfin: "Jellyfin", emby: "Emby" };

export function describeRule(rule: Rule): string {
  const values = (rule.values ?? []).filter(Boolean);
  const not = rule.negate ? " not" : "";
  switch (rule.kind) {
    case "genre":
      return `the genre is${not} ${anyOf(values) || "…"}`;
    case "rating":
      return `the age rating is${not} ${anyOf(values) || "…"}`;
    case "tag":
      return `it has${rule.negate ? " none of" : ""} the tag ${anyOf(values) || "…"}`;
    case "file_name":
      return `the file name${rule.negate ? " doesn't contain" : " contains"} ${anyOf(values.map((v) => `"${v}"`)) || "…"}`;
    case "user":
      return `${anyOf(values) || "…"} is${not} watching`;
    case "library":
      return `it's${not} in the ${anyOf(values) || "…"} library`;
    case "media_type":
      return `it's${not} ${rule.value === "episode" ? "a TV episode" : "a movie"}`;
    case "time_window":
      return `the time is${not} between ${formatTime(rule.start) || "…"} and ${formatTime(rule.end) || "…"}`;
    case "first_in_session":
      return rule.negate ? "it isn't the first episode after a break" : "it's the first episode after a break";
    case "audio_format":
      return `the sound is${not} ${anyOf(values.map((v) => AUDIO_FORMATS.find(([k]) => k === v)?.[1] ?? v)) || "…"}`;
    case "server":
      return `the media server is${not} ${anyOf(values.map((v) => SERVERS[v] ?? SERVER_LABELS[v] ?? (v.startsWith("server:") ? "a removed server" : v))) || "…"}`;
    case "trailers_available":
      return rule.negate ? "no movie trailers are ready" : "movie trailers are ready";
    default:
      return "a rule this page can't show";
  }
}

export function describeCondition(block: Block): string | null {
  const rules = block.condition?.rules ?? [];
  if (!rules.length) return null;
  const joiner = block.condition?.match === "any" ? " or " : " and ";
  return `Only if ${rules.map(describeRule).join(joiner)}`;
}
