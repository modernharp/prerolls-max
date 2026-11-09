// Rules, the never-play list, age ratings and the smart settings
// (CONTRACTS §9). Types follow the server's answers; hooks cache them.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export type MediaType = "movie" | "episode" | "any";
export type PlayOrder = "random" | "in_order";

export interface RuleWhen {
  genres: string[];
  ratings: string[];
  kids_safe: boolean;
  decades: string[];
  year_from: number | null;
  year_to: number | null;
  libraries: string[];
  users: string[];
  media_type: MediaType;
  first_episode_only: boolean;
}

export interface RulePlay {
  collection_id: number | null;
  preroll_ids: number[];
  count: number | null;
  order: PlayOrder;
  cooldown_hours: number;
}

export interface RuleIn {
  name: string;
  enabled: boolean;
  position?: number;
  when: RuleWhen;
  play: RulePlay;
}

export interface Named {
  id: number;
  name: string;
}

export interface Rule extends RuleIn {
  id: number;
  position: number;
  summary: string;
  collection_name: string | null;
  plays: Named[];
  problem: string | null;
}

export interface RulesResponse {
  rules: Rule[];
  fallback: string;
}

export interface PreviewItem {
  item_type: "Movie" | "Episode";
  item_name: string;
  genres: string[];
  tags: string[];
  official_rating: string;
  year: number | null;
  library_name: string;
  user_name: string;
  first_in_session: boolean | null;
}

export interface PreviewResult {
  excluded: boolean;
  matched: Named | null;
  explanation: string;
  would_play: Named[];
  pool: Named[];
  count: number;
  order: PlayOrder | null;
  checks: { rule_id: number; name: string; matched: boolean; why: string }[];
  fallback: string | null;
}

export interface Exclusion {
  id: number;
  kind: "item" | "title" | "tag";
  kind_label: string;
  value: string;
  note: string | null;
  created_at: string | null;
}

export interface ExclusionsResponse {
  items: Exclusion[];
  auto_tags: { enabled: boolean; tags: string[]; note: string };
}

export interface RatingFamily {
  id: string;
  name: string;
  ratings: { value: string; label: string; kids_safe: boolean }[];
}

export interface RatingsResponse {
  families: RatingFamily[];
  kids_safe: string[];
  unrated_is_kids_safe: boolean;
}

export interface SmartSettings {
  binge_window_hours: number;
  kids_safe_ratings: string[];
  unrated_is_kids_safe: boolean;
  honor_no_intro_tags: boolean;
  no_intro_tags: string[];
  history_enabled: boolean;
  history_retention_days: number;
  loudness_target_lufs: number;
  loudness_tolerance_lu: number;
  watch_sessions: boolean;
  /** "Add from a web link" may fetch from the home network (a NAS). */
  links_allow_home_network?: boolean;
  /** Newer servers only. */
  backup_includes_history?: boolean;
  plugins_updated?: { server: string; updated: boolean; message: string }[];
}

export const ruleKeys = {
  rules: ["rules"] as const,
  exclusions: ["exclusions"] as const,
  ratings: ["ratings"] as const,
  smart: ["smart-settings"] as const,
};

export function useRules() {
  return useQuery({ queryKey: ruleKeys.rules, queryFn: () => api.get<RulesResponse>("/api/rules") });
}

export function useExclusions() {
  return useQuery({ queryKey: ruleKeys.exclusions, queryFn: () => api.get<ExclusionsResponse>("/api/exclusions") });
}

export function useRatings() {
  return useQuery({ queryKey: ruleKeys.ratings, queryFn: () => api.get<RatingsResponse>("/api/ratings"), staleTime: 5 * 60_000 });
}

export function useSmartSettings() {
  return useQuery({ queryKey: ruleKeys.smart, queryFn: () => api.get<SmartSettings>("/api/smart-settings") });
}
