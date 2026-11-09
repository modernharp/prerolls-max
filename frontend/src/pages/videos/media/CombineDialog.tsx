// "Combine into one video": several intros, or a playlist, as one file. For
// apps that only play the first intro of a list (Jellyfin and Emby on Roku).
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { zChecked } from "../../../lib/schemas";
import { cleanName } from "../../../lib/validate";
import { useCategories } from "../../../lib/queries";
import { formatDuration, plural } from "../../../lib/format";
import type { CombineResult } from "../../../lib/media";
import { usePlaylists } from "../../settings/advanced/playlists/usePlaylists";
import { Modal } from "../../../components/Dialog";
import { Button } from "../../../components/Button";
import { TextField, applyServerFields } from "../../../components/Field";
import { Select } from "../../../components/Select";
import { FeatureBadges } from "../../../components/FeatureBadges";
import { ErrorNotice, Notice } from "../../../components/Notice";
import { JobProgress, useMediaJob } from "./useMediaJob";

const NONE = "none";

const schema = z
  .object({
    source: z.enum(["videos", "playlist"]),
    playlist: z.string(),
    name: zChecked((v) => cleanName(v, { what: "name" })),
    profile: z.enum(["720p", "1080p", "2160p"]),
    collection: z.string(),
    match_loudness: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.source === "playlist" && !v.playlist) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["playlist"], message: "Choose a playlist." });
  });
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function Done({ result }: { result: CombineResult }) {
  return (
    <Notice tone="success" title={`Made "${result.name}"`}>
      <p className="small">
        {plural(result.parts.length, "video")} in one file{result.duration_seconds ? `, ${formatDuration(result.duration_seconds)}` : ""}: {result.parts.join(", ")}.
      </p>
      {result.note && <p className="small">{result.note}</p>}
      <p className="small">It's in Your videos now. Put it in the collection your Roku viewers' schedule plays.</p>
    </Notice>
  );
}

export function CombineDialog({ ids, open, onClose }: { ids: number[]; open: boolean; onClose: () => void }) {
  const playlists = usePlaylists();
  const categories = useCategories();
  const run = useMediaJob<CombineResult>("/api/media/combine");
  const canUseSelection = ids.length >= 2;
  const { register, control, handleSubmit, watch, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    defaultValues: { source: "videos", playlist: "", name: "", profile: "1080p", collection: NONE, match_loudness: true },
  });
  useEffect(() => {
    if (open && !run.job) reset({ source: canUseSelection ? "videos" : "playlist", playlist: "", name: "Intros in one", profile: "1080p", collection: NONE, match_loudness: true });
  }, [open, canUseSelection, reset, run.job]);
  const source = watch("source");
  const close = () => {
    if (!run.running) run.reset();
    onClose();
  };
  const submit = (v: Output) =>
    run.start.mutate(
      {
        ...(v.source === "videos" ? { preroll_ids: ids } : { sequence_id: Number(v.playlist) }),
        name: v.name,
        profile: v.profile,
        frame_rate: "source",
        match_loudness: v.match_loudness,
        collection_id: v.collection === NONE ? null : Number(v.collection),
      },
      { onError: (error) => applyServerFields(error, setError, ["name", "collection_id", "sequence_id"]) },
    );

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && close()}
      title="Combine into one video"
      description="Some apps play only the first intro in a list. The best known is the Jellyfin app on Roku. One combined video plays in full there."
    >
      {!run.job && !run.start.isPending ? (
        <form className="stack" onSubmit={handleSubmit(submit)} noValidate>
          <FeatureBadges feature="combined_file" />
          <fieldset className="plain-fieldset">
            <legend className="field-label">Made from</legend>
            <div className="choice-grid">
              <label className="choice">
                <input type="radio" value="videos" disabled={!canUseSelection} {...register("source")} />
                <span>
                  <span className="choice-title">The {plural(ids.length, "video")} you selected</span>
                  {!canUseSelection && <span className="choice-desc">Select at least two on Your videos first.</span>}
                </span>
              </label>
              <label className="choice">
                <input type="radio" value="playlist" {...register("source")} />
                <span>
                  <span className="choice-title">A playlist</span>
                  <span className="choice-desc">Random steps are picked once, now. Make it again for a new mix.</span>
                </span>
              </label>
            </div>
          </fieldset>
          {source === "playlist" && (
            <Controller
              control={control}
              name="playlist"
              render={({ field }) => (
                <Select
                  label="Playlist"
                  value={field.value}
                  onChange={field.onChange}
                  error={errors.playlist?.message}
                  placeholder={playlists.data?.length ? "Choose a playlist" : "No playlists yet"}
                  options={(playlists.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
                />
              )}
            />
          )}
          <TextField label="Name" error={errors.name?.message} {...register("name")} />
          <div className="form-grid">
            <Controller
              control={control}
              name="profile"
              render={({ field }) => (
                <Select
                  label="Size"
                  value={field.value}
                  onChange={field.onChange}
                  options={[
                    { value: "1080p", label: "1080p" },
                    { value: "720p", label: "720p" },
                    { value: "2160p", label: "4K" },
                  ]}
                />
              )}
            />
            <Controller
              control={control}
              name="collection"
              render={({ field }) => (
                <Select
                  label="Add it to"
                  optional
                  value={field.value}
                  onChange={field.onChange}
                  options={[{ value: NONE, label: "No collection" }, ...(categories.data ?? []).filter((c) => !c.is_system).map((c) => ({ value: String(c.id), label: c.name }))]}
                />
              )}
            />
          </div>
          <label className="checkbox">
            <input type="checkbox" {...register("match_loudness")} /> Even out the loudness of each part
          </label>
          {run.start.isError && !Object.keys(errors).length && <ErrorNotice error={run.start.error} />}
          <div className="dialog-footer">
            <Button onClick={close}>Cancel</Button>
            <Button type="submit" variant="primary">
              Combine
            </Button>
          </div>
        </form>
      ) : (
        <div className="stack">
          <p className="muted small">Making one file from all the parts. This takes about as long as the videos together. You can close this and come back.</p>
          <JobProgress job={run.job} error={run.jobError} label="Combining videos">
            {run.job?.result && <Done result={run.job.result} />}
          </JobProgress>
          <div className="dialog-footer">
            <Button variant={run.finished ? "primary" : "secondary"} onClick={close}>
              {run.finished ? "Done" : "Close and keep going"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
