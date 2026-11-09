// Saved playlists: GET/POST/PUT/DELETE /sequences, export and import .nexseq.
import { useQuery } from "@tanstack/react-query";
import { api } from "../../../../lib/api";
import { sanitizeSequence, type Block, type SavedPlaylist } from "../../../../lib/playlist";

export const PLAYLISTS_KEY = ["playlists"] as const;

export function usePlaylists() {
  return useQuery({ queryKey: PLAYLISTS_KEY, queryFn: () => api.get<SavedPlaylist[]>("/sequences") });
}

export function savePlaylist(input: { id?: number; name: string; description: string; blocks: Block[] }) {
  const body = { name: input.name, description: input.description || null, blocks: sanitizeSequence(input.blocks) };
  return input.id ? api.put<SavedPlaylist>(`/sequences/${input.id}`, body) : api.post<SavedPlaylist>("/sequences", body);
}

function saveFile(text: string, filename: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function fileNameFor(name: string): string {
  const base = name.replace(/[\\/:*?"<>|,;]+/g, " ").replace(/\s+/g, " ").trim() || "Playlist";
  return `${base}.nexseq`;
}

/** Downloads a playlist as a .nexseq file other Prerolls Max (and NeXroll) installs can import. */
export async function exportPlaylist(playlist: { id?: number; name: string; description?: string | null; blocks: Block[] }) {
  const pattern = playlist.id
    ? await api.post<unknown>(`/sequences/${playlist.id}/export`, undefined, { query: { export_mode: "with_community_ids" } })
    : await api.post<unknown>("/sequences/export-pattern", {
        name: playlist.name,
        description: playlist.description ?? "",
        blocks: sanitizeSequence(playlist.blocks),
        export_mode: "with_community_ids",
      });
  saveFile(JSON.stringify(pattern, null, 2), fileNameFor(playlist.name));
}

export interface ImportResult {
  pattern_name: string;
  /** The file's name, or "Name (2)" when a playlist here already has it. */
  suggested_name?: string | null;
  pattern_description: string;
  blocks: Block[];
  match_results: { matched: number; unmatched: number; total_blocks: number; missing_categories: string[]; missing_prerolls: string[] };
}

export function importPlaylistFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api.post<ImportResult>("/sequences/import", form, { timeoutMs: 60_000 });
}

export interface StepOutcome {
  outcome: "plays" | "otherwise" | "skipped";
  block: Block | null;
  reason: string | null;
}

export function evaluatePlaylist(blocks: Block[], context: { server: string; media_type: string; genres: string }) {
  return api.post<{ blocks: StepOutcome[] }>("/sequences/evaluate-conditions", sanitizeSequence(blocks), {
    query: { server: context.server, media_type: context.media_type, genres: context.genres.trim() || undefined },
  });
}
