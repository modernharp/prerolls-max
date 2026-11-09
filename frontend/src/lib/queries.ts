// Data from the server, cached with TanStack Query. One hook per thing.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Category, FillerSettings, OnboardingStatus, Preroll, Schedule, ServerStatus } from "./types";
import type { ServerType } from "./capabilities";

export const keys = {
  categories: ["categories"] as const,
  prerolls: ["prerolls"] as const,
  schedules: ["schedules"] as const,
  active: ["active-schedules"] as const,
  server: (type: ServerType) => ["server-status", type] as const,
  filler: ["filler"] as const,
  timezone: ["timezone"] as const,
  onboarding: ["onboarding"] as const,
  trash: ["trash"] as const,
};

export function useCategories() {
  return useQuery({ queryKey: keys.categories, queryFn: () => api.get<Category[]>("/categories") });
}

export function usePrerolls() {
  return useQuery({ queryKey: keys.prerolls, queryFn: () => api.get<Preroll[]>("/prerolls") });
}

export function useSchedules() {
  return useQuery({ queryKey: keys.schedules, queryFn: () => api.get<Schedule[]>("/schedules") });
}

export function useActiveScheduleIds() {
  return useQuery({
    queryKey: keys.active,
    queryFn: async () => (await api.get<{ active_schedule_ids: number[] }>("/scheduler/active-schedule-ids")).active_schedule_ids,
    refetchInterval: 60_000,
  });
}

export function useServerStatus(type: ServerType) {
  return useQuery({
    queryKey: keys.server(type),
    queryFn: () => api.get<ServerStatus>(`/${type}/status`, undefined, { timeoutMs: 15_000 }),
    staleTime: 30_000,
    retry: false,
  });
}

export function useFiller() {
  return useQuery({ queryKey: keys.filler, queryFn: () => api.get<FillerSettings>("/settings/filler") });
}

export function useTimezone() {
  return useQuery({
    queryKey: keys.timezone,
    queryFn: async () => (await api.get<{ timezone: string }>("/settings/timezone")).timezone,
  });
}

export function useOnboarding() {
  return useQuery({ queryKey: keys.onboarding, queryFn: () => api.get<OnboardingStatus>("/onboarding/status") });
}

/** Thumbnail address for a video, or null. Thumbnails are generated on demand. */
export function thumbnailUrl(p: Pick<Preroll, "thumbnail">): string | null {
  if (!p.thumbnail) return null;
  const path = p.thumbnail.replace(/^\/+/, "").replace(/^static\//, "");
  return `/static/${path.split("/").map(encodeURIComponent).join("/")}`;
}

export function videoUrl(p: Pick<Preroll, "id">): string {
  return `/prerolls/${p.id}/video`;
}
