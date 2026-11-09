import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { keys } from "../../lib/queries";
import { isApiError } from "../../lib/errors";
import { zChecked } from "../../lib/schemas";
import { cleanName } from "../../lib/validate";
import { MESSAGES, checkWhole } from "../../lib/validateSmart";
import { useWeights } from "../../lib/media";
import { FeatureBadges } from "../../components/FeatureBadges";
import type { Category } from "../../lib/types";
import { Modal } from "../../components/Dialog";
import { TextField, applyServerFields } from "../../components/Field";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/Notice";
import { useToast } from "../../components/Toast";

const schema = z.object({
  name: zChecked((v) => cleanName(v, { what: "collection name" })),
  description: z.string().max(500, "Keep the description to 500 characters or fewer."),
  cooldown: z.string().refine((v) => !v.trim() || checkWhole(v, 0, 720, MESSAGES.cooldown).ok, MESSAGES.cooldown),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

export function CollectionDialog({ collection, onClose, onCreated }: { collection: Category | "new" | null; onClose: () => void; onCreated?: (c: Category) => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const isNew = collection === "new";
  const existingId = collection && collection !== "new" ? collection.id : undefined;
  const weights = useWeights(existingId, Boolean(existingId));
  const savedCooldown = weights.data?.cooldown_hours ?? 0;
  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    mode: "onTouched",
  });

  useEffect(() => {
    if (collection === "new") reset({ name: "", description: "", cooldown: "0" });
    else if (collection) reset({ name: collection.name, description: collection.description ?? "", cooldown: String(savedCooldown) });
  }, [collection, reset, savedCooldown]);

  const save = useMutation({
    mutationFn: async (v: Output) => {
      const saved =
        isNew || !collection
          ? await api.post<Category>("/categories", { name: v.name, description: v.description })
          : await api.put<Category>(`/categories/${collection.id}`, {
              name: v.name,
              description: v.description,
              apply_to_plex: collection.apply_to_plex,
              plex_mode: collection.plex_mode,
            });
      const hours = Number(v.cooldown.trim() || 0);
      const id = saved?.id ?? existingId;
      if (id && hours !== (isNew ? 0 : savedCooldown)) {
        await api.put(`/api/collections/${id}/cooldown`, { cooldown_hours: hours });
        await queryClient.invalidateQueries({ queryKey: ["weights"] });
      }
      return saved;
    },
    onSuccess: async (data, v) => {
      await queryClient.invalidateQueries({ queryKey: keys.categories });
      await queryClient.invalidateQueries({ queryKey: keys.prerolls });
      toast({ tone: "success", title: isNew ? `Made the "${v.name}" collection` : `Saved "${v.name}"` });
      if (isNew && data) onCreated?.(data);
      onClose();
    },
    onError: (error, v) => {
      // The server still says "Category ..." here; say it in our words.
      if (isApiError(error) && error.status === 409) {
        setError("name", { type: "server", message: `There's already a collection called "${v.name}". Pick another name.` });
        return;
      }
      applyServerFields(error, setError, ["name", "description"], [[/name|exists|already/i, "name"]]);
    },
  });

  return (
    <Modal open={Boolean(collection)} onOpenChange={(o) => !o && onClose()} title={isNew ? "New collection" : "Edit collection"}>
      <form className="stack" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
        <TextField label="Name" placeholder="For example: Halloween" error={errors.name?.message} {...register("name")} />
        <TextField label="Description" optional error={errors.description?.message} {...register("description")} />
        <div>
          <TextField
            label="Don't repeat an intro within (hours)"
            inputMode="numeric"
            help="When intros from this collection are picked at random, one that played this recently is left out while another can play. 0 means any time."
            error={errors.cooldown?.message}
            {...register("cooldown")}
          />
          <FeatureBadges feature="weights_cooldowns" />
        </div>
        {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
        <div className="dialog-footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {isNew ? "Make collection" : "Save"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
