// Advanced > Video scaling: make an intro smaller so remote viewers and
// slower devices can play it straight, without the media server converting it.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { keys, usePrerolls } from "../../../lib/queries";
import { formatSize, videoName } from "../../../lib/format";
import { Select } from "../../../components/Select";
import { Button } from "../../../components/Button";
import { FieldShell } from "../../../components/Field";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../../components/Notice";

interface VideoInfo {
  success: boolean;
  width?: number;
  height?: number;
  resolution_label?: string;
  codec?: string;
  file_size?: string | number;
  error?: string;
}

interface ConvertResult {
  success: boolean;
  message: string;
  skipped?: boolean;
  new_size_bytes?: number;
}

const SIZES = [
  { value: "1080p", label: "1080p (1920 × 1080)" },
  { value: "720p", label: "720p (1280 × 720), good for watching away from home" },
  { value: "480p", label: "480p (854 × 480), for slow connections" },
];

export function ScalingPage() {
  const prerolls = usePrerolls();
  const queryClient = useQueryClient();
  const [videoId, setVideoId] = useState("");
  const [size, setSize] = useState("720p");
  const [replace, setReplace] = useState("copy");
  const [pickError, setPickError] = useState<string>();
  const info = useQuery({
    queryKey: ["video-info", videoId],
    enabled: Boolean(videoId),
    queryFn: () => api.get<VideoInfo>(`/prerolls/${videoId}/video-info`, undefined, { timeoutMs: 40_000 }),
  });
  const convert = useMutation({
    mutationFn: () =>
      api.post<ConvertResult>(`/prerolls/${videoId}/transcode`, { resolution: size, replace_original: replace === "replace" }, { timeoutMs: 30 * 60_000 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      await queryClient.invalidateQueries({ queryKey: ["video-info", videoId] });
    },
  });

  if (prerolls.isLoading) return <Loading />;
  if (prerolls.isError) return <ErrorNotice error={prerolls.error} onRetry={() => prerolls.refetch()} />;
  const list = prerolls.data ?? [];
  if (!list.length) return <EmptyState title="No intro videos yet">Upload or download some first.</EmptyState>;

  const submit = () => {
    if (!videoId) {
      setPickError("Pick a video.");
      return;
    }
    setPickError(undefined);
    convert.mutate();
  };

  return (
    <div className="stack">
      <p className="muted">
        A 4K intro before a movie someone watches away from home makes the media server convert it on the fly, and some
        apps skip it instead. A smaller copy plays straight away. Most people never need this.
      </p>
      <section className="card stack" aria-labelledby="sc-title">
        <h2 id="sc-title">Make a smaller copy</h2>
        <Select
          label="Video"
          value={videoId}
          onChange={(v) => {
            setVideoId(v);
            setPickError(undefined);
            convert.reset();
          }}
          options={list.map((p) => ({ value: String(p.id), label: videoName(p) }))}
          placeholder="Choose a video"
          error={pickError}
        />
        {videoId && info.isLoading && <Loading label="Checking the video…" />}
        {info.data?.success && (
          <p className="small">
            Now: {info.data.width} × {info.data.height} ({info.data.resolution_label}), {info.data.codec?.toUpperCase()}
            {info.data.file_size ? `, ${formatSize(Number(info.data.file_size))}` : ""}.
          </p>
        )}
        {info.data && !info.data.success && <Notice tone="warning">Prerolls Max couldn't read this video's size. It may be damaged.</Notice>}
        <Select label="New size" value={size} onChange={setSize} options={SIZES} />
        <FieldShell label="Keep the original?" group>
          {() => (
            <div className="stack-sm">
              <label className="choice">
                <input type="radio" name="replace" value="copy" checked={replace === "copy"} onChange={() => setReplace("copy")} />
                <span>
                  <span className="choice-title">Keep both</span>
                  <span className="choice-desc">The smaller copy is added to your library next to the original.</span>
                </span>
              </label>
              <label className="choice">
                <input type="radio" name="replace" value="replace" checked={replace === "replace"} onChange={() => setReplace("replace")} />
                <span>
                  <span className="choice-title">Replace the original</span>
                  <span className="choice-desc">Saves space. The original can't be brought back.</span>
                </span>
              </label>
            </div>
          )}
        </FieldShell>
        {convert.isPending && <Notice tone="info">Converting. A short intro takes under a minute; longer ones take a few.</Notice>}
        {convert.data && <Notice tone={convert.data.skipped ? "info" : "success"}>{convert.data.skipped ? "It's already that size, so nothing changed." : `Done. The new file is ${formatSize(convert.data.new_size_bytes)}.`}</Notice>}
        {convert.isError && <ErrorNotice error={convert.error} />}
        <div>
          <Button variant="primary" onClick={submit} loading={convert.isPending}>
            Convert
          </Button>
        </div>
      </section>
    </div>
  );
}
