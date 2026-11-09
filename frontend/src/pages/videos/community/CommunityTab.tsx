// Get more from Community: Prerolls.me first, Prerolls.uk below. Pick from
// both and download them together in one go.
import { useCallback, useState } from "react";
import { Download, Search } from "lucide-react";
import { plural } from "../../../lib/format";
import { Button } from "../../../components/Button";
import { Modal } from "../../../components/Dialog";
import { Select } from "../../../components/Select";
import { ErrorNotice, Loading } from "../../../components/Notice";
import { CommunitySection } from "./CommunitySection";
import { DownloadDialog } from "./DownloadDialog";
import { attribution, useSources, watchLabel, type CommunityItem, type Filters, type Sort } from "./useCommunity";

const ORDER = ["prerollsme", "prerollsuk"];

function Preview({ item, sourceName }: { item: CommunityItem; sourceName: string }) {
  if (item.preview_url) {
    return (
      <video className="player" src={item.preview_url} controls autoPlay playsInline>
        Your browser can't play this preview.
      </video>
    );
  }
  if (item.embed_url) {
    return (
      <div className="stack-sm">
        <div className="embed-frame">
          <iframe
            src={item.embed_url}
            title={item.title}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
        <p className="muted small">
          {attribution(item, sourceName)}. This one can only be watched, not downloaded.{" "}
          <a href={item.watch_url || item.page_url} target="_blank" rel="noreferrer noopener">
            {watchLabel(item)}
          </a>
        </p>
      </div>
    );
  }
  return null;
}

export function CommunityTab() {
  const sources = useSources();
  const [filters, setFilters] = useState<Filters>({ q: "", duration: "", sort: "newest", downloadable: false });
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Map<string, CommunityItem>>(new Map());
  const [preview, setPreview] = useState<CommunityItem | null>(null);
  const [downloading, setDownloading] = useState(false);

  const toggle = (item: CommunityItem) =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(item.id)) next.delete(item.id);
      else next.set(item.id, item);
      return next;
    });
  const clear = useCallback(() => setSelected(new Map()), []);

  if (sources.isLoading) return <Loading label="Loading community libraries…" />;
  if (sources.isError || !sources.data) return <ErrorNotice error={sources.error} onRetry={() => sources.refetch()} />;

  const list = [...sources.data].sort((a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id));
  const sourceName = (id: string) => list.find((s) => s.id === id)?.name ?? "";

  return (
    <>
      <p className="muted section-gap">
        Free intros made by other people. Tick the ones you want from either library, then download them all at once.
      </p>
      <form
        className="toolbar"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters((f) => ({ ...f, q: search }));
        }}
      >
        <div className="field grow search-field">
          <label htmlFor="community-search" className="visually-hidden">
            Search community videos
          </label>
          <Search size={18} className="search-icon" aria-hidden="true" />
          <input id="community-search" className="input search-input" type="search" placeholder="Search, like 'Halloween'" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="toolbar-select">
          <Select
            label={<span className="visually-hidden">Length</span>}
            value={filters.duration || "any"}
            onChange={(v) => setFilters((f) => ({ ...f, duration: (v === "any" ? "" : v) as Filters["duration"] }))}
            options={[
              { value: "any", label: "Any length" },
              { value: "lt10", label: "Under 10 seconds" },
              { value: "10-20", label: "10 to 20 seconds" },
              { value: "20-30", label: "20 to 30 seconds" },
              { value: "30plus", label: "Over 30 seconds" },
            ]}
          />
        </div>
        <div className="toolbar-select">
          <Select
            label={<span className="visually-hidden">Order</span>}
            value={filters.sort}
            onChange={(v) => setFilters((f) => ({ ...f, sort: v as Sort }))}
            options={[
              { value: "newest", label: "Newest first" },
              { value: "popular", label: "Most downloaded" },
              { value: "shortest", label: "Shortest first" },
              { value: "az", label: "A to Z" },
            ]}
          />
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={filters.downloadable} onChange={(e) => setFilters((f) => ({ ...f, downloadable: e.target.checked }))} />
          Only ones I can download
        </label>
        <Button type="submit">Search</Button>
      </form>

      {list.map((source) => (
        <CommunitySection key={source.id} source={source} filters={filters} selected={selected} onToggle={toggle} onPreview={setPreview} />
      ))}

      {selected.size > 0 && (
        <div className="selection-bar" role="region" aria-label="Selected videos">
          <span className="grow">
            <strong>{plural(selected.size, "video")}</strong> selected
          </span>
          <Button size="sm" variant="ghost" onClick={clear}>
            Clear
          </Button>
          <Button variant="primary" icon={<Download size={18} aria-hidden="true" />} onClick={() => setDownloading(true)}>
            Download
          </Button>
        </div>
      )}

      <Modal open={Boolean(preview)} onOpenChange={(o) => !o && setPreview(null)} title={preview?.title ?? ""} wide>
        {preview && <Preview item={preview} sourceName={sourceName(preview.source)} />}
      </Modal>
      <DownloadDialog open={downloading} onOpenChange={setDownloading} items={[...selected.values()]} sources={list} onFinished={clear} />
    </>
  );
}
