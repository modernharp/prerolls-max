// Moving from NeXroll (/api/migrate/nexroll/*): the import, "is NeXroll still
// running?" and running both side by side. The words people see are built
// here so they can be tested.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { isMissingFeature } from "./errors";
import { plural } from "./format";

export type ImportMode = "replace" | "merge";
export type Manager = "prerollsmax" | "nexroll";

export interface Preview {
  source: { kind: "database" | "upload" | "running" | null; where: string | null; exported_by?: string | null; keys_left_out: boolean };
  counts: {
    collections: number;
    intro_videos: number;
    videos_found: number;
    videos_missing: number;
    videos_in_zip: number;
    schedules: number;
    playlists: number;
    holidays: number;
    genre_maps: number;
    radarr: number;
    sonarr: number;
    api_keys: number;
    users: number;
  };
  servers: { type: "plex" | "jellyfin" | "emby"; url: string; has_key: boolean; already_here: boolean }[];
  keys: string[];
  missing: { count: number; folder: string | null; examples: string[] };
  names_taken: { collections: string[]; schedules: string[]; playlists: string[] };
  library_empty: boolean;
  suggested_mode: ImportMode;
  skipped: string[];
  left_behind: string[];
}

export interface SourceResult {
  source_id: string;
  preview: Preview;
}

export interface MissingVideos {
  count: number;
  folder: string | null;
  folder_exists_here?: boolean;
  examples: string[];
}

export interface ImportReport {
  mode: ImportMode;
  added: { collections: number; intro_videos: number; schedules: number; playlists: number; holidays: number; servers: number; arr: number };
  matched: { collections: number; intro_videos: number; schedules: number; playlists: number };
  renamed: string[];
  skipped: string[];
  notes: string[];
  keys_imported: string[];
  videos_copied: number;
  settings: "replaced" | "kept";
  missing: MissingVideos;
  message: string;
  finished_at?: string;
}

export interface RelinkResult {
  relinked: number;
  still_missing: number;
  examples: string[];
  message: string;
}

export interface ServerSplit {
  id: number;
  name: string;
  type: "plex" | "jellyfin" | "emby";
  manager: Manager;
}

export interface AlongsideState {
  mode: "replace" | "alongside";
  servers: ServerSplit[];
  summary: string | null;
  conflicts: string[];
  port: {
    running: number;
    configured: number;
    source: "environment" | "settings" | "default";
    saved: number | null;
    in_docker: boolean;
    restart_needed: boolean;
  };
}

export interface MigrateStatus {
  found: { path: string; folder: string; modified: string }[];
  platform: "windows" | "docker" | "other";
  library_dir: string;
  import: { last: ImportReport | null; waiting: MissingVideos };
  alongside: AlongsideState;
}

export interface Detection {
  alongside: boolean;
  summary: string | null;
  servers: ServerSplit[];
  warnings: { id: string; severity: "warning" | "info"; server: string | null; title: string; message: string; fix: string; help: string }[];
}

export const nexrollKeys = {
  status: ["nexroll", "status"] as const,
  detect: ["nexroll", "detect"] as const,
};

export function useMigrateStatus(enabled = true) {
  return useQuery({ queryKey: nexrollKeys.status, enabled, queryFn: () => api.get<MigrateStatus>("/api/migrate/nexroll") });
}

/** Banners on Home and Media Servers. Quiet when the server doesn't have the feature. */
export function useNexrollDetect() {
  return useQuery({
    queryKey: nexrollKeys.detect,
    queryFn: async () => {
      try {
        return await api.get<Detection>("/api/migrate/nexroll/detect", { timeoutMs: 40_000 });
      } catch (error) {
        if (isMissingFeature(error)) return { alongside: false, summary: null, servers: [], warnings: [] } as Detection;
        throw error;
      }
    },
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}

/** "3 collections, 12 intro videos (10 found here, 2 missing), 4 schedules and 1 playlist". */
export function previewSummary(p: Preview): string {
  const c = p.counts;
  const videos =
    c.intro_videos === 0
      ? "no intro videos"
      : c.videos_missing
        ? `${plural(c.intro_videos, "intro video")} (${c.videos_found} found here, ${c.videos_missing} missing)`
        : `${plural(c.intro_videos, "intro video")} (all found here)`;
  const parts = [plural(c.collections, "collection"), videos, plural(c.schedules, "schedule"), plural(c.playlists, "playlist")];
  if (c.holidays) parts.push(plural(c.holidays, "holiday"));
  if (c.radarr + c.sonarr) parts.push(`${c.radarr + c.sonarr} Radarr or Sonarr ${c.radarr + c.sonarr === 1 ? "server" : "servers"}`);
  return joinWords(parts);
}

/** "Plex at http://… (with its key), Jellyfin at http://… (already here)" */
export function serverLines(p: Preview): string[] {
  const names = { plex: "Plex", jellyfin: "Jellyfin", emby: "Emby" };
  return p.servers.map(
    (s) => `${names[s.type]} at ${s.url}${s.already_here ? " (already connected here)" : s.has_key ? " (with its key)" : " (no key: add it afterwards)"}`,
  );
}

/** What the person is told when NeXroll's videos are somewhere Prerolls Max can't see. */
export function missingSentence(m: Pick<MissingVideos, "count" | "folder">): string | null {
  if (!m.count) return null;
  const videos = plural(m.count, "video");
  return m.folder
    ? `NeXroll kept ${m.count === 1 ? "a video" : videos} in ${m.folder}, and Prerolls Max can't see that folder. Point it to where they are now.`
    : `Prerolls Max can't see ${m.count === 1 ? "one video's file" : `the files of ${videos}`}. Point it to where they are now.`;
}

export function joinWords(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/** The port check the server makes, so the field says it as you type. */
export function checkPort(value: string, alongside: boolean): string | undefined {
  const text = value.trim();
  if (!text) return "Enter a port number.";
  if (!/^\d+$/.test(text)) return "Use digits only, like 9494.";
  const port = Number(text);
  if (port < 1024 || port > 65535) return "Pick a port between 1024 and 65535.";
  if (alongside && port === 9393) return "9393 is NeXroll's port. Pick another one, like 9494.";
  return undefined;
}

/** "http://192.168.1.5:9494" for the address after a restart. */
export function addressWithPort(port: number, here: Location = window.location): string {
  return `${here.protocol}//${here.hostname}:${port}`;
}
