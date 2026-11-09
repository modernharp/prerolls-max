// Add or change a watch folder: the folder, the collection new files go
// into, and whether they're used where they are or copied into the library.
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { useCategories } from "../../../lib/queries";
import { zChecked } from "../../../lib/schemas";
import { cleanFolderPath } from "../../../lib/validate";
import { mediaKeys, type WatchFolder } from "../../../lib/media";
import { Modal } from "../../../components/Dialog";
import { Button } from "../../../components/Button";
import { TextField, applyServerFields } from "../../../components/Field";
import { Select } from "../../../components/Select";
import { SwitchRow } from "../../../components/Controls";
import { ErrorNotice } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

const NONE = "none";

export const watchSchema = z.object({
  path: zChecked((v) => cleanFolderPath(v)),
  collection: z.string(),
  mode: z.enum(["link", "copy"]),
  recursive: z.boolean(),
  enabled: z.boolean(),
});
type Input = z.input<typeof watchSchema>;
type Output = z.output<typeof watchSchema>;

interface Props {
  folder: WatchFolder | "new" | null;
  onClose: () => void;
}

export function WatchFolderDialog({ folder, onClose }: Props) {
  const categories = useCategories();
  const queryClient = useQueryClient();
  const toast = useToast();
  const isNew = folder === "new";
  const { register, control, handleSubmit, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(watchSchema),
    mode: "onTouched",
  });
  useEffect(() => {
    if (folder === "new") reset({ path: "", collection: NONE, mode: "link", recursive: true, enabled: true });
    else if (folder) {
      reset({ path: folder.path, collection: folder.collection_id ? String(folder.collection_id) : NONE, mode: folder.mode, recursive: folder.recursive, enabled: folder.enabled });
    }
  }, [folder, reset]);

  const save = useMutation({
    mutationFn: (v: Output) => {
      const body = { path: v.path, collection_id: v.collection === NONE ? null : Number(v.collection), mode: v.mode, recursive: v.recursive, enabled: v.enabled };
      return isNew || !folder ? api.post<WatchFolder>("/api/watch-folders", body) : api.put<WatchFolder>(`/api/watch-folders/${folder.id}`, body);
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: mediaKeys.watch });
      toast({ tone: "success", title: isNew ? `Watching ${saved.path}` : "Saved", description: isNew ? "New videos there are added within a minute." : undefined });
      onClose();
    },
    onError: (error) => applyServerFields(error, setError, ["path", "mode"], [[/folder|path/i, "path"]]),
  });

  const collections = (categories.data ?? []).filter((c) => !c.is_system);
  return (
    <Modal open={Boolean(folder)} onOpenChange={(o) => !o && onClose()} title={isNew ? "Watch a folder" : "Change watch folder"}>
      <form className="stack" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
        <TextField
          label="Folder"
          placeholder="/downloads/intros"
          help="The full path as Prerolls Max sees it. In Docker, mount the folder into the container first and use the path inside it."
          error={errors.path?.message}
          autoComplete="off"
          spellCheck={false}
          {...register("path")}
        />
        <Controller
          control={control}
          name="collection"
          render={({ field }) => (
            <Select
              label="Add new videos to"
              value={field.value}
              onChange={field.onChange}
              options={[{ value: NONE, label: "No collection" }, ...collections.map((c) => ({ value: String(c.id), label: c.name }))]}
            />
          )}
        />
        <fieldset className="plain-fieldset">
          <legend className="field-label">How they're added</legend>
          <div className="choice-grid">
            <label className="choice">
              <input type="radio" value="link" {...register("mode")} />
              <span>
                <span className="choice-title">Use them where they are</span>
                <span className="choice-desc">Files stay in your folder. Plex must be able to see that folder too.</span>
              </span>
            </label>
            <label className="choice">
              <input type="radio" value="copy" {...register("mode")} />
              <span>
                <span className="choice-title">Copy into the library</span>
                <span className="choice-desc">A copy goes into the collection's folder. Your original stays put.</span>
              </span>
            </label>
          </div>
        </fieldset>
        <Controller
          control={control}
          name="recursive"
          render={({ field }) => <SwitchRow label="Include folders inside it" checked={field.value} onChange={field.onChange} />}
        />
        <Controller
          control={control}
          name="enabled"
          render={({ field }) => <SwitchRow label="On" description="Turn it off to stop adding new files for now." checked={field.value} onChange={field.onChange} />}
        />
        {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
        <div className="dialog-footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {isNew ? "Start watching" : "Save"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
