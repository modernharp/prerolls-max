// People who can sign in (admins only).
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserPlus } from "lucide-react";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { zChecked, zOptionalChecked } from "../../lib/schemas";
import { checkPassword, cleanName, cleanUsername } from "../../lib/validate";
import { TextField, applyServerFields } from "../../components/Field";
import { Button, IconButton } from "../../components/Button";
import { ConfirmDialog, Modal } from "../../components/Dialog";
import { ErrorNotice, Loading } from "../../components/Notice";
import { useToast } from "../../components/Toast";

interface User {
  id: number;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
}

const schema = z.object({
  username: zChecked(cleanUsername),
  display_name: zOptionalChecked((v) => cleanName(v, { maxLen: 60 })),
  password: zChecked(checkPassword),
  admin: z.boolean(),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function AddUser({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { username: "", display_name: "", password: "", admin: false },
  });
  const add = useMutation({
    mutationFn: (v: Output) =>
      api.post("/auth/users", { username: v.username, password: v.password, display_name: v.display_name || undefined, role: v.admin ? "admin" : "user" }),
    onSuccess: async (_d, v) => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      toast({ tone: "success", title: `Added ${v.username}` });
      reset();
      onOpenChange(false);
    },
    onError: (error) => applyServerFields(error, setError, ["username", "password", "display_name"], [[/password/i, "password"], [/user ?name|exists/i, "username"]]),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Add a person">
      <form className="stack" onSubmit={handleSubmit((v) => add.mutate(v))} noValidate>
        <TextField label="User name" autoCapitalize="none" help="Letters and numbers. Dots, dashes and underscores are fine too." error={errors.username?.message} {...register("username")} />
        <TextField label="Their name" optional error={errors.display_name?.message} {...register("display_name")} />
        <TextField label="Password" type="password" autoComplete="new-password" help="At least 8 characters. Avoid well-known ones like password1." error={errors.password?.message} {...register("password")} />
        <label className="checkbox">
          <input type="checkbox" {...register("admin")} /> Admin (can change settings and add people)
        </label>
        {add.isError && !Object.keys(errors).length && <ErrorNotice error={add.error} />}
        <div className="dialog-footer">
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" variant="primary" loading={add.isPending}>
            Add person
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function UsersSection() {
  const { status } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<User | null>(null);
  const users = useQuery({ queryKey: ["users"], queryFn: async () => (await api.get<{ users: User[] }>("/auth/users")).users });

  return (
    <div className="stack">
      <div className="row-between">
        <h3>People who can sign in</h3>
        <Button size="sm" icon={<UserPlus size={16} aria-hidden="true" />} onClick={() => setAdding(true)}>
          Add a person
        </Button>
      </div>
      {users.isLoading ? (
        <Loading />
      ) : users.isError ? (
        <ErrorNotice error={users.error} onRetry={() => users.refetch()} />
      ) : (
        <ul className="list">
          {(users.data ?? []).map((u) => (
            <li key={u.id} className="list-row">
              <div className="grow">
                <strong>{u.display_name || u.username}</strong>
                <div className="muted small">
                  {u.username} · {u.role === "admin" ? "Admin" : "Can change intros"}
                  {!u.is_active ? " · Turned off" : ""}
                </div>
              </div>
              {u.id !== status?.user?.id && (
                <IconButton label={`Remove ${u.username}`} onClick={() => setRemoving(u)}>
                  <Trash2 size={18} aria-hidden="true" />
                </IconButton>
              )}
            </li>
          ))}
        </ul>
      )}
      <AddUser open={adding} onOpenChange={setAdding} />
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? `Remove ${removing.username}?` : ""}
        body={<p>They won't be able to sign in any more. Intros and schedules aren't affected.</p>}
        confirmLabel="Remove"
        danger
        onConfirm={async () => {
          if (!removing) return;
          await api.del(`/auth/users/${removing.id}`);
          await queryClient.invalidateQueries({ queryKey: ["users"] });
          toast({ tone: "success", title: `Removed ${removing.username}` });
        }}
      />
    </div>
  );
}
