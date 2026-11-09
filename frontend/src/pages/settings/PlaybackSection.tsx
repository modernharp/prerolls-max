// Settings, Playback: binge gap, kids-safe ratings, no-intro tags, play
// history, loudness target and session watching (PUT /api/smart-settings).
import { useEffect } from "react";
import { Controller, useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ruleKeys, useRatings, useSmartSettings, type SmartSettings } from "../../lib/rules";
import { joinList, playbackSchema, type PlaybackInput, type PlaybackOutput } from "../../lib/validateSmart";
import { FieldShell, TextField, applyServerFields } from "../../components/Field";
import { SwitchRow, ToggleChips } from "../../components/Controls";
import { Button } from "../../components/Button";
import { ErrorNotice, Loading, Notice } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { useToast } from "../../components/Toast";

const FIELDS = Object.keys(playbackSchema.shape);

function toForm(s: SmartSettings): PlaybackInput {
  return {
    binge_window_hours: String(s.binge_window_hours),
    kids_safe_ratings: s.kids_safe_ratings,
    unrated_is_kids_safe: s.unrated_is_kids_safe,
    honor_no_intro_tags: s.honor_no_intro_tags,
    no_intro_tags: joinList(s.no_intro_tags),
    history_enabled: s.history_enabled,
    history_retention_days: String(s.history_retention_days),
    loudness_target_lufs: String(s.loudness_target_lufs),
    loudness_tolerance_lu: String(s.loudness_tolerance_lu),
    watch_sessions: s.watch_sessions,
    links_allow_home_network: Boolean(s.links_allow_home_network),
  };
}

export function PlaybackSection() {
  const settings = useSmartSettings();
  const ratings = useRatings();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { register, control, handleSubmit, reset, watch, setError, formState: { errors, isDirty } } = useForm<PlaybackInput, unknown, PlaybackOutput>({
    // The resolver turns the text boxes into numbers and lists.
    resolver: zodResolver(playbackSchema) as unknown as Resolver<PlaybackInput, unknown, PlaybackOutput>,
    mode: "onTouched",
  });
  useEffect(() => {
    if (settings.data) reset(toForm(settings.data));
  }, [settings.data, reset]);

  const save = useMutation({
    mutationFn: (v: PlaybackOutput) => api.put<SmartSettings>("/api/smart-settings", v),
    onSuccess: async (data) => {
      queryClient.setQueryData(ruleKeys.smart, data);
      await queryClient.invalidateQueries({ queryKey: ruleKeys.ratings });
      await queryClient.invalidateQueries({ queryKey: ruleKeys.exclusions });
      const pushed = data.plugins_updated ?? [];
      const failed = pushed.filter((p) => !p.updated);
      toast({
        tone: failed.length ? "info" : "success",
        title: "Playback settings saved",
        description: pushed.length ? pushed.map((p) => p.message).join(" ") : undefined,
      });
    },
    onError: (error) => applyServerFields(error, setError, FIELDS),
  });

  if (settings.isLoading) return <Loading />;
  if (settings.isError) return <ErrorNotice error={settings.error} onRetry={() => settings.refetch()} />;
  const honorTags = watch("honor_no_intro_tags");
  const history = watch("history_enabled");

  return (
    <form className="stack" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
      <h3>TV shows</h3>
      <TextField
        label="Break between episodes (hours)"
        inputMode="numeric"
        help="An episode counts as the first of a binge when the same person hasn't started an episode of that show for this long. Prerolls Max also sets it in the plugin on Jellyfin and Emby."
        error={errors.binge_window_hours?.message}
        className="input-short"
        {...register("binge_window_hours")}
      />

      <h3>Kids-safe</h3>
      {ratings.data && (
        <Controller
          control={control}
          name="kids_safe_ratings"
          render={({ field }) => (
            <FieldShell label="Ratings that count as kids-safe" group help="Rules with Kids-safe ticked match titles with any of these ratings." error={errors.kids_safe_ratings?.message}>
              {(ids) => (
                <div className="stack-sm">
                  {ratings.data.families
                    .filter((f) => f.id !== "unrated")
                    .map((f) => (
                      <div key={f.id} className="stack-sm">
                        <span className="muted small">{f.name}</span>
                        <ToggleChips
                          describedBy={ids.describedBy}
                          options={f.ratings.map((r) => ({ value: r.value, label: r.value }))}
                          selected={field.value ?? []}
                          onChange={field.onChange}
                        />
                      </div>
                    ))}
                </div>
              )}
            </FieldShell>
          )}
        />
      )}
      <Controller
        control={control}
        name="unrated_is_kids_safe"
        render={({ field }) => (
          <SwitchRow
            label="Treat unrated titles as kids-safe"
            description="Off is safer: an unrated title is as likely to be a director's cut as a home video."
            checked={field.value}
            onChange={field.onChange}
          />
        )}
      />

      <h3>Never play an intro</h3>
      <Controller
        control={control}
        name="honor_no_intro_tags"
        render={({ field }) => (
          <SwitchRow
            label="Skip intros for titles with a no-intro tag"
            description="Tag a movie or show in Jellyfin or Emby and it never gets an intro. Plex can't do this."
            checked={field.value}
            onChange={field.onChange}
          />
        )}
      />
      {honorTags && (
        <TextField label="No-intro tags" help="Separate several with commas. Upper and lower case don't matter." error={errors.no_intro_tags?.message} {...register("no_intro_tags")} />
      )}

      <h3>Play history</h3>
      <Controller
        control={control}
        name="history_enabled"
        render={({ field }) => (
          <SwitchRow
            label="Remember which intros played"
            description="Needed for What Played, the missed-intro check and 'don't repeat within'."
            checked={field.value}
            onChange={field.onChange}
          />
        )}
      />
      {history && (
        <TextField
          label="Keep history for (days)"
          inputMode="numeric"
          help="Older plays are forgotten on their own."
          error={errors.history_retention_days?.message}
          className="input-short"
          {...register("history_retention_days")}
        />
      )}
      <Controller
        control={control}
        name="watch_sessions"
        render={({ field }) => (
          <div>
            <SwitchRow
              label="Spot intros that didn't play"
              description="Prerolls Max looks at what your media servers are playing and warns on Home when a movie started without its intro."
              checked={field.value}
              onChange={field.onChange}
            />
            <FeatureBadges feature="missed_intro_check" />
          </div>
        )}
      />

      <h3>Loudness</h3>
      <p className="muted small">
        Films and TV are mixed to about -23 LUFS, so an intro at -23 sits right next to the movie after it. The -16 you may see
        for streaming is for phones and podcasts, and would make an intro noticeably louder than the film.
      </p>
      <div className="form-grid">
        <TextField
          label="Target (LUFS)"
          inputMode="decimal"
          help="From -31 to -10. -23 is the TV standard."
          error={errors.loudness_target_lufs?.message}
          {...register("loudness_target_lufs")}
        />
        <TextField
          label="Allowed difference (LU)"
          inputMode="decimal"
          help="How far from the target still counts as even. 2 is about what you'd notice."
          error={errors.loudness_tolerance_lu?.message}
          {...register("loudness_tolerance_lu")}
        />
      </div>

      <h3>Adding videos</h3>
      <Controller
        control={control}
        name="links_allow_home_network"
        render={({ field }) => (
          <SwitchRow
            label="Allow links to my home network"
            description="Lets Add from a web link download from a NAS or another computer at home, like http://192.168.1.20/intro.mp4. Leave it off unless you need it: with it off, a link can only reach sites on the internet."
            checked={field.value}
            onChange={field.onChange}
          />
        )}
      />

      {Object.keys(errors).length > 0 && <Notice tone="error" title="Some settings need fixing">Check the fields marked in red.</Notice>}
      {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
      <div className="form-actions">
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!isDirty && !save.isError}>
          Save playback settings
        </Button>
        {isDirty && (
          <Button onClick={() => settings.data && reset(toForm(settings.data))} disabled={save.isPending}>
            Undo changes
          </Button>
        )}
      </div>
    </form>
  );
}
