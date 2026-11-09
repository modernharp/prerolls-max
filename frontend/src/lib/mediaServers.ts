// Every Plex, Jellyfin and Emby server (GET /api/servers). Several of one
// type are fine: each has its own name, address, key and on/off switch.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { isMissingFeature } from "./errors";
import type { ServerType } from "./capabilities";

export interface ServerLiveStatus {
  connected: boolean;
  reachable?: boolean;
  signed_in?: boolean;
  message?: string | null;
  hint?: string | null;
  version?: string | null;
  server_name?: string | null;
}

export interface PlexApplyStatus {
  state: "ok" | "failed" | "waiting";
  message: string;
  at: string;
  missing?: number;
}

export interface MediaServer {
  id: number;
  type: ServerType;
  type_label: string;
  name: string;
  url: string;
  enabled: boolean;
  /** The first switched-on server of its type: older pages and scripts act on it. */
  primary: boolean;
  version: string | null;
  has_key: boolean;
  plugin_key: { id: number; name: string; active: boolean } | null;
  mappings?: { local: string; plex: string }[];
  last_apply?: PlexApplyStatus | null;
  status?: ServerLiveStatus;
  /** "nexroll" when NeXroll keeps this server (Settings > Moving from NeXroll). */
  managed_by?: "prerollsmax" | "nexroll";
}

export interface TestStep {
  id: string;
  title: string;
  state: "ok" | "warn" | "fail" | "skipped";
  detail: string | null;
  link: { to: string; label: string } | null;
}

export interface PlayTestReason {
  title: string;
  detail: string;
  link: { to: string; label: string } | null;
}

export interface PlayTestResult {
  server: { id: number; name: string; type: ServerType };
  movie: { id: string; title: string };
  ok: boolean;
  items: { title: string; preroll_id: number | null }[];
  summary: string;
  reasons: PlayTestReason[];
}

export interface Movie {
  id: string;
  title: string;
  year: number | null;
}

export const serversKey = (check: boolean) => ["media-servers", check] as const;

/** Names of named servers in "server" playlist rules ("server:<id>"), kept fresh by useMediaServers. */
export const SERVER_LABELS: Record<string, string> = {};

/** The server list; `check` also asks each server whether it answers. */
export function useMediaServers(check = false) {
  return useQuery({
    queryKey: serversKey(check),
    queryFn: async () => {
      try {
        const servers = (await api.get<{ servers: MediaServer[] }>("/api/servers", check ? { check: true } : undefined, { timeoutMs: 30_000 })).servers;
        for (const s of servers) SERVER_LABELS[`server:${s.id}`] = s.name;
        return servers;
      } catch (error) {
        if (isMissingFeature(error)) return [];
        throw error;
      }
    },
    staleTime: check ? 30_000 : 10_000,
    retry: false,
  });
}

/** "Jellyfin", then "Jellyfin 2"... the name the server suggests for a new one. */
export function suggestName(servers: Pick<MediaServer, "name">[], label: string): string {
  const taken = new Set(servers.map((s) => s.name.trim().toLocaleLowerCase()));
  if (!taken.has(label.toLocaleLowerCase())) return label;
  let n = 2;
  while (taken.has(`${label} ${n}`.toLocaleLowerCase())) n += 1;
  return `${label} ${n}`;
}

/** Whether another server already uses this name (names ignore case). */
export function nameTaken(name: string, servers: Pick<MediaServer, "id" | "name">[], exceptId?: number): boolean {
  const wanted = name.trim().replace(/\s+/g, " ").toLocaleLowerCase();
  return servers.some((s) => s.id !== exceptId && s.name.trim().toLocaleLowerCase() === wanted);
}

export function byType(servers: MediaServer[], type: ServerType): MediaServer[] {
  return servers.filter((s) => s.type === type);
}
