import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { keys, useCategories } from "../../lib/queries";
import { zChecked } from "../../lib/schemas";
import { cleanName } from "../../lib/validate";
import { videoName } from "../../lib/format";
import { MESSAGES, weightLabel } from "../../lib/validateSmart";
import { FeatureBadges } from "../../components/FeatureBadges";
import type { Preroll } from "../../lib/types";
import { Modal } from "../../components/Dialog";
import { FieldShell, TextField, applyServerFields } from "../../components/Field";
import { ToggleChips } from "../../components/Controls";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/Notice";
import { useToast } from "../../components/Toast";

const schema = z.object({
  display_name: zChecked((v) => cleanName(v, { what: "name", maxLen: 100 })),
  category_ids: z.array(z.number()),
  weight: z.number().int().min(1, MESSAGES.weight).max(10, MESSAGES.weight),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

export function EditVideoDialog({ preroll, onClose }: { preroll: Preroll | null; onClose: () => void }) {
  const categories = useCategories();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { register, control, handleSubmit, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    mode: "onTouched",
  });

  useEffect(() => {
    if (preroll) reset({ display_name: videoName(preroll), category_ids: preroll.categories.map((c) => c.id), weight: preroll.weight ?? 5 });
  }, [preroll, reset]);

  const save = useMutation({
    mutationFn: async ({ weight, ...values }: Output) => {
      await api.put(`/prerolls/${preroll?.id}`, values);
      if (preroll && weight !== (preroll.weight ?? 5)) await api.put("/api/weights", { items: [{ preroll_id: preroll.id, weight }] });
    },
    onSuccess: async (_d, values) => {
      await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      toast({ tone: "success", title: `Saved "${values.display_name}"` });
      onClose();
    },
    onError: (error) => applyServerFields(error, setError, ["display_name", "category_ids", "weight"]),
  });

  return (
    <Modal open={Boolean(preroll)} onOpenChange={(o) => !o && onClose()} title="Edit intro video">
      <form className="stack" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
        <TextField label="Name" help="Only changes the name shown here. The file keeps its name." error={errors.display_name?.message} {...register("display_name")} />
        <Controller
          control={control}
          name="category_ids"
          render={({ field }) => (
            <FieldShell label="Collections" group help="Pick any number. Schedules play videos from collections.">
              {(ids) =>
                categories.data?.length ? (
                  <ToggleChips
                    describedBy={ids.describedBy}
                    options={categories.data.map((c) => ({ value: c.id, label: c.name }))}
                    selected={field.value ?? []}
                    onChange={field.onChange}
                  />
                ) : (
                  <p className="muted small">No collections yet. Make one on the Collections tab.</p>
                )
              }
            </FieldShell>
          )}
        />
        <Controller
          control={control}
          name="weight"
          render={({ field }) => (
            <FieldShell
              label="How often"
              help="Only matters when intros are picked at random. Normal is 5; 10 plays twice as often as 5, and 1 plays rarely."
              error={errors.weight?.message}
            >
              {(ids) => (
                <div className="weight-row">
                  <span className="muted small" aria-hidden="true">Rarely</span>
                  <input
                    id={ids.id}
                    type="range"
                    min={1}
                    max={10}
                    step={1}
                    className="range"
                    value={field.value ?? 5}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                    aria-describedby={ids.describedBy}
                    aria-valuetext={`${field.value ?? 5} of 10: ${weightLabel(field.value ?? 5)}`}
                  />
                  <span className="muted small" aria-hidden="true">Often</span>
                  <output htmlFor={ids.id} className="badge badge-accent weight-value">
                    {weightLabel(field.value ?? 5)} ({field.value ?? 5})
                  </output>
                </div>
              )}
            </FieldShell>
          )}
        />
        <FeatureBadges feature="weights_cooldowns" />
        {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
        <div className="dialog-footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}
