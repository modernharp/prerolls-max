// "When": the conditions of a rule. Every condition filled in must be true;
// a list is true when any entry is. Empty means "doesn't matter".
import { Controller, type UseFormReturn } from "react-hook-form";
import { Link } from "react-router-dom";
import { DECADES, type RuleDraft } from "../../lib/validateSmart";
import { useRatings } from "../../lib/rules";
import { FieldShell, TextField } from "../../components/Field";
import { SwitchRow, ToggleChips } from "../../components/Controls";
import { RatingPicker } from "./RatingPicker";

export function RuleWhenFields({ form }: { form: UseFormReturn<RuleDraft> }) {
  const { register, control, watch, formState: { errors } } = form;
  const ratings = useRatings();
  const mediaType = watch("media_type");
  const kidsSafe = watch("kids_safe");
  const kidsList = ratings.data?.kids_safe ?? [];

  return (
    <section className="card stack" aria-labelledby="when-title">
      <div>
        <h2 id="when-title">When</h2>
        <p className="muted">Fill in only what matters. Everything you fill in must be true for the rule to match.</p>
      </div>

      <FieldShell label="Before" group>
        {() => (
          <div className="choice-grid">
            {(
              [
                ["any", "Movies and episodes"],
                ["movie", "Movies only"],
                ["episode", "TV episodes only"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="choice">
                <input type="radio" value={value} {...register("media_type")} />
                <span className="choice-title">{label}</span>
              </label>
            ))}
          </div>
        )}
      </FieldShell>

      {mediaType !== "movie" && (
        <Controller
          control={control}
          name="first_episode_only"
          render={({ field }) => (
            <div>
              <SwitchRow
                label="Only the first episode of a binge"
                description="Plays before the first episode someone starts after a break, not before every episode. The break is set in Settings, Playback (4 hours unless you change it)."
                checked={field.value}
                onChange={field.onChange}
              />
              {errors.first_episode_only && <p className="field-error">{errors.first_episode_only.message}</p>}
            </div>
          )}
        />
      )}

      <div>
        <TextField
          label="Genres"
          optional
          help='Separate several with commas. Matches when the title has any of them. "Sci-Fi" also matches "Science Fiction".'
          placeholder="Animation, Family"
          error={errors.genres?.message}
          {...register("genres")}
        />
      </div>

      <Controller
        control={control}
        name="kids_safe"
        render={({ field }) => (
          <div className={`kids-box ${field.value ? "on" : ""}`}>
            <SwitchRow
              label="Kids-safe titles"
              description={
                <>
                  Matches titles rated {kidsList.length ? kidsList.join(", ") : "G, PG, TV-Y, TV-G and similar"}.{" "}
                  {ratings.data?.unrated_is_kids_safe ? "Unrated titles count too." : "Unrated titles don't count."} Change
                  the list in <Link to="/settings#playback">Settings, Playback</Link>.
                </>
              }
              checked={field.value}
              onChange={field.onChange}
            />
          </div>
        )}
      />

      {ratings.data && (
        <Controller
          control={control}
          name="ratings"
          render={({ field }) => (
            <div>
              <RatingPicker families={ratings.data.families} value={field.value} onChange={field.onChange} error={errors.ratings?.message} />
              {kidsSafe && field.value.length > 0 && (
                <p className="muted small">With Kids-safe on as well, a title must be kids-safe and have one of these ratings.</p>
              )}
            </div>
          )}
        />
      )}

      <div className="stack-sm">
        <Controller
          control={control}
          name="decades"
          render={({ field }) => (
            <FieldShell label="Decades" optional group help="Matches titles that came out in any of these decades.">
              {(ids) => (
                <ToggleChips describedBy={ids.describedBy} options={DECADES.map((d) => ({ value: d, label: d }))} selected={field.value} onChange={field.onChange} />
              )}
            </FieldShell>
          )}
        />
        <div className="form-grid">
          <TextField label="From the year" optional inputMode="numeric" placeholder="1980" error={errors.year_from?.message} {...register("year_from")} />
          <TextField label="To the year" optional inputMode="numeric" placeholder="1989" error={errors.year_to?.message} {...register("year_to")} />
        </div>
      </div>

      <div className="form-grid">
        <div>
          <TextField
            label="Libraries"
            optional
            help="Library names as your media server shows them. Separate several with commas."
            placeholder="Kids Movies"
            error={errors.libraries?.message}
            {...register("libraries")}
          />
        </div>
        <div>
          <TextField
            label="Who's watching"
            optional
            help="User names on Jellyfin or Emby. Separate several with commas."
            placeholder="Mia, Leo"
            error={errors.users?.message}
            {...register("users")}
          />
        </div>
      </div>
    </section>
  );
}
