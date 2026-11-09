// What each media server can do with intros (CONTRACTS §6), from
// GET /api/capabilities. The built-in table below only fills in when an
// older server doesn't have that endpoint.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { isMissingFeature } from "./errors";

export type ServerType = "plex" | "jellyfin" | "emby";
export type Level = "native" | "plugin" | "emulated" | "none";
export type Feature =
  | "random" | "sequence" | "random_in_groups" | "folders" | "genre_rules" | "rating_rules"
  | "per_user" | "per_library" | "episodes" | "first_episode_only" | "time_of_day" | "dates"
  | "trailers" | "on_resume" | "client_notes"
  // Smart features (CONTRACTS §9)
  | "rule_sets" | "exclude_titles" | "kids_safe" | "year_rules" | "weights_cooldowns" | "play_history"
  | "missed_intro_check" | "combined_file" | "loudness" | "matching_versions" | "watch_folders";

export interface FeatureInfo {
  level: Level;
  note: string;
}

export interface PluginState {
  connected: boolean;
  version: string | null;
  protocol: number | string | null;
  last_seen_seconds_ago: number | null;
  note: string;
}

export interface ServerCapabilities {
  type: ServerType;
  connected: boolean;
  configured?: boolean;
  version?: string | null;
  /** "server_list" (Plex) or "plugin" (Jellyfin, Emby). */
  delivery?: string;
  plugin?: PluginState;
  features: Partial<Record<Feature, FeatureInfo>>;
  /** Each server of this type (several are allowed), with its own plugin state. */
  instances?: ServerInstance[];
}

export interface ServerInstance {
  id: number;
  type: ServerType;
  name: string;
  enabled: boolean;
  connected: boolean;
  version: string | null;
  plugin?: PluginState;
}

export const SERVER_NAMES: Record<ServerType, string> = { plex: "Plex", jellyfin: "Jellyfin", emby: "Emby" };

export const FEATURE_LABELS: Record<Feature, string> = {
  random: "Pick one intro at random",
  sequence: "Play several intros in order",
  random_in_groups: "Random picks from several collections",
  folders: "Use a whole folder",
  genre_rules: "Different intros by genre",
  rating_rules: "Different intros by age rating",
  per_user: "Different intros for each person",
  per_library: "Different intros for each library",
  episodes: "Intros before TV episodes",
  first_episode_only: "Only before the first episode",
  time_of_day: "Different intros by time of day",
  dates: "Intros for dates and holidays",
  trailers: "Movie trailers before the film",
  on_resume: "Intro when you resume a movie",
  client_notes: "Works in every app",
  rule_sets: "Rules for different titles",
  exclude_titles: "Never-play list",
  kids_safe: "Kids-safe titles",
  year_rules: "Release year and decade",
  weights_cooldowns: "How often and no repeats",
  play_history: "What played",
  missed_intro_check: "Spots missed intros",
  combined_file: "One combined video",
  loudness: "Even loudness",
  matching_versions: "TV-friendly versions",
  watch_folders: "Watch folders",
};

const f = (level: Level, note: string): FeatureInfo => ({ level, note });

// Only used when Prerolls Max can't be asked (an older server without
// /api/capabilities). Copied from GET /api/capabilities, November 2026.
export const BUILTIN: Record<ServerType, ServerCapabilities["features"]> = {
  plex: {
    random: f("native", "Plex picks one intro from the list at random each time a movie starts."),
    sequence: f("native", "Plex plays the whole list in order before each movie; a list longer than about 7,500 characters is cut to its first entries."),
    random_in_groups: f("emulated", "Plex can't pick within groups, so Prerolls Max picks one per group and writes them in order; the picks change when it rewrites the list, not on every play."),
    folders: f("emulated", "Plex can't read a folder, so Prerolls Max lists its files for Plex; very large folders are cut to fit Plex's limit."),
    genre_rules: f("emulated", "Plex picks the intro before it knows the movie, so genre rules apply from the next play, and only while one person is watching."),
    rating_rules: f("emulated", "Plex picks the intro before it knows the movie, so age-rating rules apply from the next play, and only while one person is watching."),
    per_user: f("emulated", "Plex has one intro list for everyone; Prerolls Max follows the one person watching for their next play and leaves it alone when several are watching."),
    per_library: f("emulated", "Plex can only switch intros off for a whole library (in the library's settings); different intros per library work from the next play only."),
    episodes: f("none", "Plex only plays intros before movies."),
    first_episode_only: f("none", "Plex doesn't play intros before episodes."),
    time_of_day: f("emulated", "Prerolls Max rewrites Plex's list when the time comes, so a movie started just before keeps the earlier intro."),
    dates: f("native", "Prerolls Max changes Plex's list when a date or holiday schedule starts and ends."),
    trailers: f("native", "Plex can add trailers itself (new releases need Plex Pass), and Prerolls Max can put trailers it downloaded into the list."),
    on_resume: f("none", "Plex doesn't play intros when a movie is resumed."),
    client_notes: f("emulated", "Plex's 2026 apps for iPhone, iPad, Apple TV, Android TV and Fire TV skip intros set to \"Play pre-roll only\"; set Cinema Trailers to \"1 before movie\" and turn Plex's own trailer sources off. Plex Web and the desktop app play them; Infuse, DLNA and downloads never do."),
  },
  jellyfin: {
    random: f("plugin", "Prerolls Max picks for every play."),
    sequence: f("plugin", "Jellyfin plays them in order before each item."),
    random_in_groups: f("plugin", "Prerolls Max picks within each group for every play."),
    folders: f("plugin", "Prerolls Max picks from the folder's files for every play."),
    genre_rules: f("plugin", "Exact: the plugin tells Prerolls Max the genres of what is about to play."),
    rating_rules: f("plugin", "Exact: the plugin tells Prerolls Max the age rating of what is about to play."),
    per_user: f("plugin", "Exact: the plugin says who is watching."),
    per_library: f("plugin", "Exact: the plugin says which library the item is in."),
    episodes: f("plugin", "Before episodes too, but only before the first one you start, not between auto-played episodes; the Android TV app plays intros before movies only."),
    first_episode_only: f("plugin", "The plugin says whether an episode is the first one someone starts after a break (4 hours by default, set on the plugin page)."),
    time_of_day: f("plugin", "Decided at the moment each play starts."),
    dates: f("plugin", "Decided at the moment each play starts."),
    trailers: f("plugin", "Jellyfin has no trailer feed of its own; trailers Prerolls Max downloads play through the plugin."),
    on_resume: f("none", "Jellyfin doesn't play intros when something is resumed."),
    client_notes: f("emulated", "The web app, Jellyfin Media Player, Android and Kodi play intros (Cinema mode must be on in the app, which it is by default). Swiftfin, Infuse and the MPV Shim don't play them, and the official Roku app plays only the first."),
  },
  emby: {
    random: f("plugin", "Prerolls Max picks for every play."),
    sequence: f("plugin", "Emby plays them in order before each item."),
    random_in_groups: f("plugin", "Prerolls Max picks within each group for every play."),
    folders: f("plugin", "Prerolls Max picks from the folder's files for every play."),
    genre_rules: f("plugin", "Exact: the plugin tells Prerolls Max the genres of what is about to play."),
    rating_rules: f("plugin", "Exact: the plugin tells Prerolls Max the age rating of what is about to play."),
    per_user: f("plugin", "Exact: the plugin says who is watching."),
    per_library: f("plugin", "Exact: the plugin says which library the item is in."),
    episodes: f("plugin", "Before episodes too; Emby's Android TV and Fire TV apps play intros before movies only."),
    first_episode_only: f("plugin", "The plugin says whether an episode is the first one someone starts after a break (4 hours by default, set on the plugin page)."),
    time_of_day: f("plugin", "Decided at the moment each play starts."),
    dates: f("plugin", "Decided at the moment each play starts."),
    trailers: f("native", "Emby can add trailers itself with Premiere, and trailers Prerolls Max downloads play through the plugin."),
    on_resume: f("none", "Emby doesn't play intros when something is resumed."),
    client_notes: f("emulated", "Needs Emby Premiere, and Cinema Intros turned on in each app (Settings, Playback). Roku has it off by default; Samsung TVs and Infuse don't play intros."),
  },
};

interface CapabilitiesResponse {
  servers: ServerCapabilities[];
}

export interface CapabilitiesResult {
  servers: ServerCapabilities[];
  /** True when the server didn't answer and the built-in table is shown. */
  builtin: boolean;
}

export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<CapabilitiesResult> => {
      try {
        const data = await api.get<CapabilitiesResponse>("/api/capabilities");
        return { servers: data.servers, builtin: false };
      } catch (error) {
        if (!isMissingFeature(error)) throw error;
        return {
          builtin: true,
          servers: (Object.keys(BUILTIN) as ServerType[]).map((type) => ({ type, connected: false, features: BUILTIN[type] })),
        };
      }
    },
  });
}

export type Tone = "success" | "accent" | "warning" | "neutral";

/**
 * The badge text for one feature on one server. `pluginWorking`: the
 * Prerolls Max plugin on that server has checked in (capabilities say so),
 * so "Needs plugin" becomes "Works (plugin)".
 */
export function badgeFor(level: Level, server: ServerType, pluginWorking = false): { label: string; tone: Tone } {
  switch (level) {
    case "native":
      return { label: "Works", tone: "success" };
    case "plugin":
      return pluginWorking ? { label: "Works (plugin)", tone: "success" } : { label: "Needs plugin", tone: "accent" };
    case "emulated":
      return { label: "Next play only", tone: "warning" };
    default:
      return { label: `Not possible on ${SERVER_NAMES[server]}`, tone: "neutral" };
  }
}

/** True when this server's plugin is installed and has asked for intros. */
export function pluginWorking(server?: Pick<ServerCapabilities, "connected" | "plugin">): boolean {
  return Boolean(server?.plugin?.connected && server.plugin.version);
}
