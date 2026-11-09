// "Play": what a matching rule plays: a collection or chosen videos, how
// many, random or in order, and how long before an intro may repeat.
import { Controller, type UseFormReturn } from "react-hook-form";
import { useCategories, usePrerolls } from "../../lib/queries";
import type { RuleDraft } from "../../lib/validateSmart";
import { FieldShell, TextField } from "../../components/Field";
import { Select } from "../../components/Select";
import { VideoPicker } from "./VideoPicker";

export function RulePlayFields({ form }: { form: UseFormReturn<RuleDraft> }) {
  const { register, control, watch, formState: { errors } } = form;
  const categories = useCategories();
  const prerolls = usePrerolls();
  const source = watch("source");
  const order = watch("order");
  const collections = (categories.data ?? []).filter((c) => !c.is_system);

  return (
    <section className="card stack" aria-labelledby="play-title">
      <h2 id="play-title">Play</h2>

      <FieldShell label="From" group>
        {() => (
          <div className="choice-grid">
            <label className="choice">
              <input type="radio" value="collection" {...register("source")} />
              <span className="choice-title">A collection</span>
            </label>
            <label className="choice">
              <input type="radio" value="videos" {...register("source")} />
              <span className="choice-title">Videos I choose</span>
            </label>
          </div>
        )}
      </FieldShell>

      {source === "collection" ? (
        <Controller
          control={control}
          name="collection_id"
          render={({ field }) => (
            <Select
              label="Collection"
              value={field.value}
              onChange={field.onChange}
              error={errors.collection_id?.message}
              placeholder={collections.length ? "Choose a collection" : "No collections yet"}
              options={collections.map((c) => ({ value: String(c.id), label: c.name }))}
              help={!collections.length ? "Make one on Intro Videos, Collections." : undefined}
            />
          )}
        />
      ) : (
        <Controller
          control={control}
          name="preroll_ids"
          render={({ field }) => (
            <VideoPicker videos={prerolls.data ?? []} value={field.value} onChange={field.onChange} ordered={order === "in_order"} error={errors.preroll_ids?.message} />
          )}
        />
      )}

      <FieldShell label="How they're picked" group>
        {() => (
          <div className="choice-grid">
            <label className="choice">
              <input type="radio" value="random" {...register("order")} />
              <span>
                <span className="choice-title">At random</span>
                <span className="choice-desc">A different one each time.</span>
              </span>
            </label>
            <label className="choice">
              <input type="radio" value="in_order" {...register("order")} />
              <span>
                <span className="choice-title">In order</span>
                <span className="choice-desc">The same ones, one after another.</span>
              </span>
            </label>
          </div>
        )}
      </FieldShell>

      <div className="form-grid">
        <TextField
          label="How many"
          optional
          inputMode="numeric"
          placeholder={order === "random" ? "1" : "All"}
          help={order === "random" ? "Leave empty to play 1." : "Leave empty to play them all."}
          error={errors.count?.message}
          {...register("count")}
        />
        {order === "random" && (
          <div>
            <TextField
              label="Don't repeat an intro within"
              inputMode="numeric"
              help="Hours. 0 means intros can repeat any time. If every intro played recently, the one that played longest ago goes."
              error={errors.cooldown_hours?.message}
              {...register("cooldown_hours")}
            />
          </div>
        )}
      </div>
    </section>
  );
}
