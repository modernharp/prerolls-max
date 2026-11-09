// Community libraries API (CONTRACTS §5) and background jobs.
import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { jobRunning, useJob, type Job } from "../../../lib/jobs";

export { jobRunning, useJob, type Job };

export type SourceId = "prerollsme" | "prerollsuk";

export interface CommunitySource {
  id: SourceId;
  name: string;
  site_url: string;
  description: string;
  item_count: number;
  downloadable_count: number;
  last_refreshed: string | null;
  refreshing: boolean;
  terms: { summary: string; url: string; needs_acceptance: boolean; accepted: boolean };
  error: null | { message: string; hint?: string };
}

export interface CommunityItem {
  id: string;
  source: SourceId;
  title: string;
  description: string | null;
  category: { slug: string; name: string } | null;
  tags: string[];
  creator: { name: string; url: string | null } | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  size_bytes: number | null;
  thumbnail_url: string | null;
  preview_url: string | null;
  embed_url: string | null;
  watch_url?: string | null;
  hosted_on?: string | null;
  page_url: string;
  downloadable: boolean;
  platforms: string[];
  attribution?: string;
  versions?: { id: string; platform: string; title: string }[];
  in_library: { preroll_id: number; name: string } | null;
}

export interface ItemPage {
  items: CommunityItem[];
  page: number;
  limit: number;
  total: number;
  total_pages: number;
}


export interface DownloadResult {
  added: { item_id: string; preroll_id: number; name: string; title: string }[];
  skipped: { item_id: string; preroll_id?: number; name?: string; title?: string }[];
  collection: { id: number; name: string } | null;
}

export type Sort = "newest" | "popular" | "shortest" | "az";

export interface Filters {
  q: string;
  duration: "" | "lt10" | "10-20" | "20-30" | "30plus";
  sort: Sort;
  downloadable: boolean;
}

const SOURCES_KEY = ["community", "sources"] as const;

export function useSources() {
  return useQuery({
    queryKey: SOURCES_KEY,
    queryFn: () => api.get<CommunitySource[]>("/api/community/sources"),
    refetchInterval: (q) => (q.state.data?.some((s) => s.refreshing) ? 3000 : false),
  });
}

export function useItems(source: SourceId, filters: Filters, page: number, enabled: boolean) {
  return useQuery({
    queryKey: ["community", "items", source, filters, page],
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: () =>
      api.get<ItemPage>("/api/community/items", {
        source,
        q: filters.q.trim(),
        duration: filters.duration,
        sort: filters.q.trim() ? undefined : filters.sort,
        downloadable: filters.downloadable ? "true" : undefined,
        page,
        limit: 24,
      }),
  });
}


/** "Check for new videos": starts the refresh job and follows it. */
export function useRefresh(source: SourceId) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const start = useMutation({
    mutationFn: () => api.post<{ job_id: string }>(`/api/community/sources/${source}/refresh`, {}),
    onSuccess: (res) => setJobId(res.job_id),
  });
  const state = job.data?.state;
  useEffect(() => {
    if (state === "done" || state === "failed") void queryClient.invalidateQueries({ queryKey: ["community"] });
  }, [state, queryClient]);
  return { start, job: job.data, jobError: job.error, running: start.isPending || jobRunning(job.data) };
}

export function useAcceptTerms(source: SourceId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/api/community/sources/${source}/accept-terms`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["community"] }),
  });
}

export function attribution(item: CommunityItem, sourceName: string): string {
  if (item.attribution) return item.attribution;
  return item.creator?.name ? `by ${item.creator.name} · via ${sourceName}` : `via ${sourceName}`;
}

export function watchLabel(item: CommunityItem): string {
  const where = item.hosted_on ?? item.embed_url ?? item.page_url;
  if (/youtu/i.test(where)) return "Watch on YouTube";
  if (/vimeo/i.test(where)) return "Watch on Vimeo";
  return "Watch on the website";
}

/**
 * The source's description with any built-in estimate ("about 1,800 intro
 * videos") replaced by the live count, so the page never shows two numbers.
 */
export function liveDescription(source: Pick<CommunitySource, "description" | "item_count">): string {
  const estimate = /\babout [\d,.]+ (intro )?videos\b/i;
  if (!estimate.test(source.description)) return source.description;
  if (source.item_count > 0) {
    return source.description.replace(estimate, (m) => `${source.item_count.toLocaleString("en-US")} ${/intro/i.test(m) ? "intro " : ""}videos`);
  }
  return source.description.replace(estimate, (m) => (/intro/i.test(m) ? "intro videos" : "videos"));
}

/** "Plex, Jellyfin and Emby versions" for Prerolls.uk rows that fold several files into one. */
export function versionsText(item: CommunityItem): string | null {
  const platforms = [...new Set((item.versions ?? []).map((v) => v.platform).filter(Boolean))];
  if (platforms.length < 2) return null;
  const names = platforms.map((p) => p.charAt(0).toUpperCase() + p.slice(1));
  const last = names.pop();
  return `${names.join(", ")} and ${last} versions`;
}
