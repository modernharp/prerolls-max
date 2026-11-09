// Play history, stats and the missed-intro check (CONTRACTS §9).
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { ServerType } from "./capabilities";

export interface Play {
  id: number;
  played_at: string | null;
  preroll_id: number | null;
  name: string;
  server_type: ServerType | string | null;
  server_name: string | null;
  user_name: string | null;
  client: string | null;
  device: string | null;
  item_name: string | null;
  item_type: string | null;
  source: "plugin" | "plex_sessions" | string;
  rule_name: string | null;
}

export interface HistoryNote {
  history_enabled: boolean;
  retention_days: number;
  note: string;
}

export interface RecentResponse extends HistoryNote {
  items: Play[];
}

export interface TopItem {
  preroll_id: number;
  name: string;
  plays: number;
  last_played: string | null;
}

export interface NeverPlayedItem {
  preroll_id: number;
  name: string;
  collections: string[];
  added: string | null;
}

export interface Count {
  name: string;
  plays: number;
}

export interface Summary extends HistoryNote {
  days: number | null;
  total_plays: number;
  by_user: Count[];
  by_server: Count[];
  by_client: Count[];
  by_day: { date: string; plays: number }[];
}

export interface HealthWarning {
  id: string;
  severity: "warning" | "info";
  server: ServerType | string | null;
  client: string | null;
  title: string;
  reason: string;
  fix: string;
  count: number;
  last_seen: string | null;
  examples: { at: string | null; title: string | null; user: string | null; device: string | null }[];
}

export interface IntroHealth {
  status: "ok" | "info" | "warning" | "unknown";
  message: string;
  days: number;
  playbacks: number;
  with_intros: number;
  watching: Partial<Record<ServerType, { ok: boolean; message: string; seconds_ago: number | null }>>;
  warnings: HealthWarning[];
}

export interface StatsFilters {
  days: number;
  server: string;
  user: string;
}

export const statsKeys = {
  all: ["stats"] as const,
  recent: (f: StatsFilters) => ["stats", "recent", f] as const,
  top: (f: StatsFilters, order: "most" | "least") => ["stats", "top", order, f] as const,
  never: (days: number) => ["stats", "never", days] as const,
  summary: (days: number) => ["stats", "summary", days] as const,
  health: ["health-intros"] as const,
};

const query = (f: StatsFilters) => ({ days: f.days, server: f.server || undefined, user: f.user || undefined });

export function useRecentPlays(f: StatsFilters) {
  return useQuery({ queryKey: statsKeys.recent(f), queryFn: () => api.get<RecentResponse>("/api/stats/recent", { ...query(f), limit: 50 }) });
}

export function useTopPlays(f: StatsFilters, order: "most" | "least") {
  return useQuery({
    queryKey: statsKeys.top(f, order),
    queryFn: () => api.get<{ items: TopItem[] }>("/api/stats/top", { ...query(f), order, limit: 10 }),
  });
}

export function useNeverPlayed(days: number) {
  return useQuery({ queryKey: statsKeys.never(days), queryFn: () => api.get<{ items: NeverPlayedItem[]; note: string }>("/api/stats/never-played", { days, limit: 50 }) });
}

export function useStatsSummary(days: number) {
  return useQuery({ queryKey: statsKeys.summary(days), queryFn: () => api.get<Summary>("/api/stats/summary", { days }) });
}

export function useIntroHealth() {
  return useQuery({
    queryKey: statsKeys.health,
    queryFn: () => api.get<IntroHealth>("/api/health/intros", { days: 7 }),
    refetchInterval: 60_000,
  });
}

/** "5 min ago", "3 hours ago", "Nov 2" for a time in the past. */
export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "";
  const minutes = Math.round((now - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
