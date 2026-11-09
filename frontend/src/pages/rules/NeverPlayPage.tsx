// The never-play list: titles, item ids or tags that never get an intro.
// Checked before rules and schedules (Jellyfin and Emby only).
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Ban, Plus, Tag, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { zChecked } from "../../lib/schemas";
import { cleanName } from "../../lib/validate";
import { ruleKeys, useExclusions, type Exclusion } from "../../lib/rules";
import { Button, IconButton } from "../../components/Button";
import { TextField, applyServerFields } from "../../components/Field";
import { Select } from "../../components/Select";
import { ConfirmDialog } from "../../components/Dialog";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { useToast } from "../../components/Toast";
import { DecisionOrder, WhenHeader } from "../schedules/WhenTabs";

const KINDS = {
  title: { label: "Title", placeholder: "Stop Making Sense", help: "The title as your media server shows it. A show's title covers all its episodes." },
  item: { label: "Item id", placeholder: "a1b2c3d4e5f6", help: "The id from the item's address in Jellyfin or Emby. A show's id covers all its episodes." },
  tag: { label: "Tag", placeholder: "Concert", help: "Any tag you use in Jellyfin or Emby. Everything with this tag is skipped." },
} as const;
type Kind = keyof typeof KINDS;

const schema = z.object({
  kind: z.enum(["title", "item", "tag"]),
  value: zChecked((v) => cleanName(v, { what: "title, id or tag", maxLen: 300 })),
  note: z.string().max(300, "Keep the note to 300 characters or fewer."),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function AddForm() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { register, control, handleSubmit, watch, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    defaultValues: { kind: "title", value: "", note: "" },
  });
  const kind = watch("kind") as Kind;
  const add = useMutation({
    mutationFn: (v: Output) => api.post<Exclusion>("/api/exclusions", { kind: v.kind, value: v.value, note: v.note.trim() || undefined }),
    onSuccess: async (row) => {
      await queryClient.invalidateQueries({ queryKey: ruleKeys.exclusions });
      toast({ tone: "success", title: `"${row.value}" never gets an intro now` });
      reset({ kind: row.kind, value: "", note: "" });
    },
    onError: (error) => applyServerFields(error, setError, ["value", "note", "kind"]),
  });
  return (
    <form className="card stack" onSubmit={handleSubmit((v) => add.mutate(v))} noValidate aria-labelledby="add-title">
      <h2 id="add-title">Add to the list</h2>
      <div className="exclusion-grid">
        <Controller
          control={control}
          name="kind"
          render={({ field }) => (
            <Select label="By" value={field.value} onChange={field.onChange} options={(Object.keys(KINDS) as Kind[]).map((k) => ({ value: k, label: KINDS[k].label }))} />
          )}
        />
        <TextField label={KINDS[kind].label} placeholder={KINDS[kind].placeholder} help={KINDS[kind].help} error={errors.value?.message} {...register("value")} />
        <TextField label="Note" optional placeholder="Why it's here" error={errors.note?.message} {...register("note")} />
      </div>
      {add.isError && !Object.keys(errors).length && <ErrorNotice error={add.error} />}
      <div>
        <Button type="submit" variant="primary" icon={<Plus size={18} aria-hidden="true" />} loading={add.isPending}>
          Add
        </Button>
      </div>
    </form>
  );
}

export default function NeverPlayPage() {
  const list = useExclusions();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [removing, setRemoving] = useState<Exclusion | null>(null);
  const items = list.data?.items ?? [];
  const auto = list.data?.auto_tags;

  const remove = async (e: Exclusion) => {
    await api.del(`/api/exclusions/${e.id}`);
    await queryClient.invalidateQueries({ queryKey: ruleKeys.exclusions });
    toast({ tone: "success", title: `"${e.value}" can get intros again` });
  };

  return (
    <>
      <WhenHeader helpSlug="never-play" />
      <DecisionOrder current={0} />
      <div className="row section-gap">
        <span className="muted small">The never-play list works on:</span>
        <FeatureBadges feature="exclude_titles" />
      </div>
      <div className="stack">
      {auto && (
        <Notice tone="info" title={auto.enabled ? "Tagged titles are skipped already" : "Tags are turned off"}>
          {auto.enabled ? (
            <p>
              In Jellyfin or Emby, give a movie or show the tag <Tag size={14} aria-hidden="true" /> <strong>{auto.tags[0] ?? "no-intro"}</strong>
              {auto.tags.length > 1 && <> (or {auto.tags.slice(1).map((t) => `"${t}"`).join(", ")})</>} and it never gets an intro. You don't
              need to add it here.
            </p>
          ) : (
            <p>The no-intro tags are ignored right now.</p>
          )}
          <p>
            Change the tags in <Link to="/settings#playback">Settings, Playback</Link>. Plex can't skip intros for one title. There you
            can only turn Cinema Trailers off for a whole library, in that library's settings.
          </p>
        </Notice>
      )}
      <AddForm />
      <section className="section" aria-labelledby="list-title">
        <h2 id="list-title">On the list</h2>
        {list.isLoading ? (
          <Loading />
        ) : list.isError ? (
          <ErrorNotice error={list.error} onRetry={() => list.refetch()} />
        ) : !items.length ? (
          <EmptyState icon={<Ban size={40} />} title="Nothing on the list yet">
            Add concert films, home videos or anything else that should start straight away.
          </EmptyState>
        ) : (
          <ul className="list">
            {items.map((e) => (
              <li key={e.id} className="list-row">
                <span className="badge">{e.kind_label}</span>
                <div className="grow">
                  <strong>{e.value}</strong>
                  {e.note && <div className="muted small">{e.note}</div>}
                </div>
                <IconButton label={`Remove ${e.value} from the list`} onClick={() => setRemoving(e)}>
                  <Trash2 size={18} aria-hidden="true" />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </section>
      </div>
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? `Take "${removing.value}" off the list?` : ""}
        body={<p>Intros will play before it again, from the next play.</p>}
        confirmLabel="Take it off"
        onConfirm={() => (removing ? remove(removing) : undefined)}
      />
    </>
  );
}
