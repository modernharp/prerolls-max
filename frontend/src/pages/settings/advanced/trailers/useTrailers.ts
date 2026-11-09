// Movie trailers (the server calls them NeX-Up): settings, Radarr/Sonarr,
// upcoming lists and downloaded trailers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Query } from "../../../../lib/api";

export interface TrailerSettings {
  enabled: boolean;
  radarr_url: string | null;
  radarr_connected: boolean;
  sonarr_enabled: boolean;
  sonarr_url: string | null;
  sonarr_connected: boolean;
  storage_path: string | null;
  recommended_storage_path: string;
  storage_path_needs_mapping_warning: boolean;
  quality: string;
  days_ahead: number;
  max_trailers: number;
  max_storage_gb: number;
  trailers_per_playback: number;
  trailer_retention_days: number;
  trailer_language: string;
  trailer_languages?: { code: string; name: string }[] | Record<string, string>;
  tmdb_api_key: string | null;
  last_sync: string | null;
  next_sync: string | null;
  last_sonarr_sync: string | null;
  coming_soon_list_auto_regen?: boolean;
  coming_soon_list_auto_regen_layout?: string;
}

export const SETTINGS_KEY = ["trailer-settings"] as const;

export function useTrailerSettings() {
  return useQuery({ queryKey: SETTINGS_KEY, queryFn: () => api.get<TrailerSettings>("/nexup/settings") });
}

/** PUT /nexup/settings takes its fields in the query string. */
export function useSaveTrailerSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: Query) => api.put<TrailerSettings>("/nexup/settings", undefined, { query: changes }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SETTINGS_KEY }),
  });
}

export type ArrKind = "radarr" | "sonarr";

export interface ArrServer {
  id: number;
  name: string;
  url: string;
}

export function useArrServers(kind: ArrKind, enabled: boolean) {
  return useQuery({
    queryKey: ["arr-servers", kind],
    enabled,
    queryFn: async () => (await api.get<{ servers: ArrServer[] }>(`/nexup/${kind}/servers`)).servers,
  });
}

/** The *arr endpoints answer 200 with {success: false, message} when the test fails. */
export interface ArrResult {
  success: boolean;
  message?: string;
}

export interface UpcomingMovie {
  radarr_id: number;
  title: string;
  year?: number;
  release_date?: string | null;
  release_type?: string | null;
  poster_url?: string | null;
  downloaded: boolean;
  available_now?: boolean;
}

export interface UpcomingShow {
  sonarr_id?: number;
  title: string;
  season_number?: number;
  /** The day the season starts, as Sonarr's calendar has it. */
  release_date?: string | null;
  release_type?: "new_show" | "new_season" | string | null;
  available_now?: boolean;
  downloaded?: boolean;
}

export interface DownloadedTrailer {
  id: number;
  title: string;
  year?: number | null;
  release_date?: string | null;
  days_until?: number | null;
  file_size?: number | null;
  removal_date?: string | null;
}
