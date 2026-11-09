// API keys for other apps (dashboards, scripts) and the plugins.
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { api } from "../../../lib/api";
import { zChecked } from "../../../lib/schemas";
import { cleanName } from "../../../lib/validate";
import { formatDateTime } from "../../../lib/format";
import type { ApiKey } from "../../../lib/types";
import { TextField, applyServerFields } from "../../../components/Field";
import { SecretValue } from "../../../components/SecretField";
import { Select } from "../../../components/Select";
import { Button, IconButton } from "../../../components/Button";
import { ConfirmDialog, Modal } from "../../../components/Dialog";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

const schema = z.object({
  name: zChecked((v) => cleanName(v, { what: "key name", maxLen: 60 })),
  permissions: z.enum(["read", "full"]),
  expires: z.enum(["never", "30", "90", "365"]),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function NewKey({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [created, setCreated] = useState<string | null>(null);
  const { register, control, handleSubmit, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { name: "", permissions: "read", expires: "never" },
  });
  const create = useMutation({
    mutationFn: (v: Output) =>
      api.post<{ key: string }>("/api/keys", {
        name: v.name,
        permissions: v.permissions,
        expires_days: v.expires === "never" ? undefined : Number(v.expires),
      }),
    onSuccess: async (res) => {
      setCreated(res.key);
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (error) => applyServerFields(error, setError, ["name"], [[/name/i, "name"]]),
  });
  const close = (o: boolean) => {
    if (!o) {
      setCreated(null);
      reset();
    }
    onOpenChange(o);
  };
  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created);
      toast({ tone: "success", title: "Key copied" });
    } catch {
      toast({ tone: "error", title: "Couldn't copy", description: "Select the key and copy it yourself." });
    }
  };

  return (
    <Modal open={open} onOpenChange={close} title={created ? "Your new key" : "New API key"}>
      {created ? (
        <div className="stack">
          <Notice tone="warning" title="Copy it now">This is the only time the whole key is shown.</Notice>
          <SecretValue value={created} what="new API key" />
          <div className="dialog-footer">
            <Button icon={<Copy size={18} aria-hidden="true" />} onClick={copy}>Copy key</Button>
            <Button variant="primary" onClick={() => close(false)}>Done</Button>
          </div>
        </div>
      ) : (
        <form className="stack" onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <TextField label="Name" placeholder="For example: Home dashboard" help="So you remember what uses it." error={errors.name?.message} {...register("name")} />
          <Controller control={control} name="permissions" render={({ field }) => (
            <Select label="What can it do?" value={field.value} onChange={field.onChange} options={[{ value: "read", label: "Only look (read)" }, { value: "full", label: "Look and change things" }]} />
          )} />
          <Controller control={control} name="expires" render={({ field }) => (
            <Select label="Stops working after" value={field.value} onChange={field.onChange} options={[{ value: "never", label: "Never" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "1 year" }]} />
          )} />
          {create.isError && !Object.keys(errors).length && <ErrorNotice error={create.error} />}
          <div className="dialog-footer">
            <Button onClick={() => close(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={create.isPending}>Make key</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export function ApiKeysPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<ApiKey | null>(null);
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: async () => (await api.get<{ keys: ApiKey[] }>("/api/keys")).keys });

  return (
    <div className="stack">
      <div className="row-between">
        <p className="muted grow">A key lets another app use Prerolls Max without your password. Send it in the X-Api-Key header.</p>
        <Button variant="primary" icon={<Plus size={18} aria-hidden="true" />} onClick={() => setCreating(true)}>New key</Button>
      </div>
      {keys.isLoading ? (
        <Loading />
      ) : keys.isError ? (
        <ErrorNotice error={keys.error} onRetry={() => keys.refetch()} />
      ) : !keys.data?.length ? (
        <EmptyState icon={<KeyRound size={36} />} title="No API keys">Make one when an app or script asks for a Prerolls Max API key.</EmptyState>
      ) : (
        <ul className="list">
          {keys.data.map((k) => (
            <li key={k.id} className="list-row">
              <KeyRound size={22} aria-hidden="true" className="muted" />
              <div className="grow">
                <strong>{k.name}</strong> <code>{k.key_prefix}…</code>{" "}
                {k.is_active === false && <span className="badge">Turned off</span>}
                <div className="muted small">
                  {k.is_active === false && "Replaced by a newer key; it no longer works. You can delete it. "}
                  {k.permissions === "read" ? "Only looks" : "Can change things"}
                  {" · "}
                  {k.last_used_at ? `Last used ${formatDateTime(k.last_used_at)}` : "Never used"}
                  {k.expires_at ? ` · Stops working ${formatDateTime(k.expires_at)}` : ""}
                </div>
              </div>
              <IconButton label={`Delete key ${k.name}`} onClick={() => setRemoving(k)}>
                <Trash2 size={18} aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
      <NewKey open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? `Delete the key "${removing.name}"?` : ""}
        body={<p>Anything using this key stops working straight away.</p>}
        confirmLabel="Delete key"
        danger
        onConfirm={async () => {
          if (!removing) return;
          await api.del(`/api/keys/${removing.id}`);
          await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
          toast({ tone: "success", title: `Deleted the key "${removing.name}"` });
        }}
      />
    </div>
  );
}
