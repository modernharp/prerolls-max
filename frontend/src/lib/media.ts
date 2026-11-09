// Media tools (loudness, TV-friendly versions, combined files), weights
// and cooldowns, and watch folders (CONTRACTS §9).
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export type LoudnessStatus = "unchecked" | "ok" | "loud" | "quiet" | "peaks" | "silent";

export interface LoudnessItem {
  preroll_id: number;
  name: string;
  lufs: number | null;
  peak: number | null;
  lra: number | null;
  checked_at: string | null;
  status: LoudnessStatus;
  label: string;
  version_of: number | null;
}

export interface LoudnessOverview {
  target_lufs: number;
  tolerance_lu: number;
  median_lufs: number | null;
  counts: Partial<Record<LoudnessStatus, number>>;
  outliers: LoudnessItem[];
  items: LoudnessItem[];
  note: string;
}

export interface MediaStatus {
  ffmpeg: boolean;
  tonemap: boolean;
  profiles: { id: "720p" | "1080p" | "2160p"; label: string }[];
  frame_rates: string[];
  note: string | null;
}

export interface NormalizeResult {
  target_lufs: number;
  mode: "new_version" | "replace";
  items: { preroll_id: number; name: string; new_preroll_id: number | null; before_lufs: number; after_lufs: number | null; original_in_trash?: boolean }[];
}

export interface VersionsResult {
  made: { preroll_id: number; name: string; profile: string; new_preroll_id: number; format: string; was: string; tone_mapped: boolean }[];
  skipped: { preroll_id: number; name: string; profile: string; why: string }[];
  note: string | null;
}

export interface CombineResult {
  preroll_id: number;
  name: string;
  duration_seconds: number | null;
  format: string;
  parts: string[];
  note: string | null;
}

export interface WeightsResponse {
  items: { preroll_id: number; name: string; weight: number; last_played: string | null; resting_until: string | null }[];
  cooldown_hours: number;
  collection: { id: number; name: string } | null;
  note: string;
}

export interface WatchFolder {
  id: number;
  path: string;
  collection_id: number | null;
  collection_name: string | null;
  mode: "link" | "copy";
  recursive: boolean;
  enabled: boolean;
  exists: boolean;
  imported_count: number;
  /** Files left out because the same video is already in the library. */
  duplicate_count?: number;
  last_checked_at: string | null;
  problem: string | null;
  waiting: { name: string; seconds?: number; why: string }[];
}

export interface WatchCheckResult {
  imported: { preroll_id: number; name: string }[];
  waiting: { name: string; why: string }[];
  errors: (string | { name?: string; message?: string })[];
  note: string;
}

export const mediaKeys = {
  loudness: ["media", "loudness"] as const,
  status: ["media", "status"] as const,
  weights: (collectionId?: number) => ["weights", collectionId ?? "all"] as const,
  watch: ["watch-folders"] as const,
};

export function useLoudness() {
  return useQuery({ queryKey: mediaKeys.loudness, queryFn: () => api.get<LoudnessOverview>("/api/media/loudness") });
}

export function useMediaStatus() {
  return useQuery({ queryKey: mediaKeys.status, queryFn: () => api.get<MediaStatus>("/api/media/status"), staleTime: 10 * 60_000 });
}

export function useWeights(collectionId?: number, enabled = true) {
  return useQuery({
    queryKey: mediaKeys.weights(collectionId),
    enabled,
    queryFn: () => api.get<WeightsResponse>("/api/weights", { collection_id: collectionId }),
  });
}

export function useWatchFolders() {
  return useQuery({
    queryKey: mediaKeys.watch,
    queryFn: () => api.get<WatchFolder[]>("/api/watch-folders"),
    // Files waiting to settle show up within half a minute.
    refetchInterval: 15_000,
  });
}

/** "Too loud (-12.4 LUFS)"-style words for a loudness status. */
export function loudnessWords(item: Pick<LoudnessItem, "status" | "lufs" | "peak">, target: number): { label: string; tone: "success" | "warning" | "neutral" | "danger"; detail: string } {
  const lufs = item.lufs === null ? null : `${item.lufs.toFixed(1)} LUFS`;
  const diff = item.lufs === null ? 0 : Math.abs(item.lufs - target);
  switch (item.status) {
    case "ok":
      return { label: "Loudness OK", tone: "success", detail: `${lufs}, close to your target of ${target} LUFS.` };
    case "loud":
      return { label: "Too loud", tone: "warning", detail: `${lufs}: about ${diff.toFixed(0)} LU louder than your target of ${target} LUFS.` };
    case "quiet":
      return { label: "Too quiet", tone: "warning", detail: `${lufs}: about ${diff.toFixed(0)} LU quieter than your target of ${target} LUFS.` };
    case "peaks":
      return { label: "Clips", tone: "warning", detail: `${lufs}, but its loudest moments clip (peak ${item.peak?.toFixed(1)} dB). Evening it out fixes that.` };
    case "silent":
      return { label: "No sound", tone: "neutral", detail: "This intro has no sound, so there's nothing to even out." };
    default:
      return { label: "Not checked", tone: "neutral", detail: "Its loudness hasn't been checked yet. Use Check loudness." };
  }
}
