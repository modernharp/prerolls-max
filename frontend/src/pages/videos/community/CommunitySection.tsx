// One community library (Prerolls.me or Prerolls.uk): its terms, its list
// (fetched once, then refreshed on request) and its videos, a page at a time.
import { useEffect, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { formatDateTime, plural } from "../../../lib/format";
import { isApiError } from "../../../lib/errors";
import { Button } from "../../../components/Button";
import { EmptyState, ErrorNotice, Loading, Notice, ProgressBar } from "../../../components/Notice";
import { CommunityItemCard } from "./CommunityItemCard";
import { liveDescription, useAcceptTerms, useItems, useRefresh, type CommunityItem, type CommunitySource, type Filters } from "./useCommunity";

interface Props {
  source: CommunitySource;
  filters: Filters;
  selected: Map<string, CommunityItem>;
  onToggle: (item: CommunityItem) => void;
  onPreview: (item: CommunityItem) => void;
}

function Terms({ source }: { source: CommunitySource }) {
  const accept = useAcceptTerms(source.id);
  return (
    <Notice tone="info" title={`Before you browse ${source.name}`}>
      <p>{source.terms.summary}</p>
      <p>
        <a href={source.terms.url} target="_blank" rel="noreferrer noopener">
          Read the full policy
        </a>
      </p>
      {accept.isError && <ErrorNotice error={accept.error} />}
      <div className="notice-action">
        <Button size="sm" variant="primary" loading={accept.isPending} onClick={() => accept.mutate()}>
          I agree
        </Button>
      </div>
    </Notice>
  );
}

function RefreshProgress({ refresh, label }: { refresh: ReturnType<typeof useRefresh>; label: string }) {
  if (!refresh.job && !refresh.start.isPending) return null;
  const job = refresh.job;
  if (job?.state === "failed") return <Notice tone="error" title="The list didn't update">{job.message}</Notice>;
  if (job?.state === "done") return null;
  return (
    <div className="stack-sm" aria-live="polite">
      <ProgressBar value={job?.progress ?? 0} label={`Updating the ${label} list`} />
      <p className="muted small">{job?.message || "Starting…"}</p>
    </div>
  );
}

export function CommunitySection({ source, filters, selected, onToggle, onPreview }: Props) {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [filters]);
  const needsTerms = source.terms.needs_acceptance && !source.terms.accepted;
  const neverLoaded = !source.last_refreshed && source.item_count === 0;
  const refresh = useRefresh(source.id);
  const busy = refresh.running || source.refreshing;
  const items = useItems(source.id, filters, page, !needsTerms && !neverLoaded && !busy);
  const data = items.data;
  const needsRefresh = isApiError(items.error) && items.error.code === "needs_refresh";

  return (
    <section className="section community-section" aria-labelledby={`src-${source.id}`}>
      <div className="row-between">
        <div className="grow">
          <h2 id={`src-${source.id}`} className="row">
            {source.name}
            <a href={source.site_url} target="_blank" rel="noreferrer noopener" className="small" aria-label={`Open the ${source.name} website`}>
              <ExternalLink size={16} aria-hidden="true" />
            </a>
          </h2>
          <p className="muted small">
            {liveDescription(source)}
            {source.item_count > 0 && source.downloadable_count < source.item_count && ` ${source.downloadable_count} of them can be downloaded.`}
            {source.last_refreshed ? ` List updated ${formatDateTime(source.last_refreshed)}.` : ""}
          </p>
        </div>
        {!needsTerms && !neverLoaded && (
          <Button
            size="sm"
            icon={<RefreshCw size={16} className={busy ? "spinner" : ""} aria-hidden="true" />}
            onClick={() => refresh.start.mutate()}
            disabled={busy}
          >
            {busy ? "Updating…" : "Check for new videos"}
          </Button>
        )}
      </div>

      {source.error && (
        <Notice tone="warning" title={source.error.message}>
          {source.error.hint}
        </Notice>
      )}
      {refresh.start.isError && <ErrorNotice error={refresh.start.error} />}
      <RefreshProgress refresh={refresh} label={source.name} />

      {needsTerms ? (
        <Terms source={source} />
      ) : neverLoaded || needsRefresh ? (
        <EmptyState
          title={`${source.name} hasn't been loaded yet`}
          action={
            <Button variant="primary" loading={busy} onClick={() => refresh.start.mutate()}>
              Get the list
            </Button>
          }
        >
          Prerolls Max downloads the list of videos once and keeps it. It takes about a minute.
        </EmptyState>
      ) : busy && !data ? (
        <Loading label="Updating the list…" />
      ) : items.isLoading ? (
        <Loading />
      ) : items.isError ? (
        <ErrorNotice error={items.error} onRetry={() => items.refetch()} />
      ) : !data?.items.length ? (
        <EmptyState title="Nothing found here">Try other words, or clear the length filter.</EmptyState>
      ) : (
        <>
          <p className="muted small" aria-live="polite">
            {plural(data.total, "video")}
            {filters.q.trim() ? ` match "${filters.q.trim()}"` : ""}
          </p>
          <ul className="video-grid">
            {data.items.map((item) => (
              <CommunityItemCard
                key={item.id}
                item={item}
                sourceName={source.name}
                selected={selected.has(item.id)}
                onToggle={() => onToggle(item)}
                onPreview={() => onPreview(item)}
              />
            ))}
          </ul>
          {data.total_pages > 1 && (
            <nav className="pager" aria-label={`${source.name} pages`}>
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <span className="muted small">
                Page {data.page} of {data.total_pages}
              </span>
              <Button size="sm" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
