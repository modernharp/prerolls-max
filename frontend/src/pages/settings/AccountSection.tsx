// Account & login: change your password, turn sign-in on or off.
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { AUTH_KEY, useAuth } from "../../lib/auth";
import { confirmPassword, withConfirm, zChecked } from "../../lib/schemas";
import { checkPassword } from "../../lib/validate";
import { TextField, applyServerFields } from "../../components/Field";
import { SwitchRow } from "../../components/Controls";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { ErrorNotice, Loading } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { UsersSection } from "./UsersSection";

const pwSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: zChecked(checkPassword),
    confirm: z.string(),
  })
  .superRefine((v, ctx) => confirmPassword(v.new_password, v.confirm, ctx));
type PwInput = z.input<typeof pwSchema>;
type PwOutput = z.output<typeof pwSchema>;

function ChangePassword() {
  const toast = useToast();
  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<PwInput, unknown, PwOutput>({
    resolver: withConfirm(zodResolver(pwSchema), "new_password"),
    mode: "onTouched",
  });
  const save = useMutation({
    mutationFn: (v: PwOutput) =>
      api.post("/auth/change-password", { current_password: v.current_password, new_password: v.new_password }, { quietAuth: true }),
    onSuccess: () => {
      reset({ current_password: "", new_password: "", confirm: "" });
      toast({ tone: "success", title: "Password changed", description: "Other devices have been signed out." });
    },
    onError: (error) =>
      applyServerFields(error, setError, ["current_password", "new_password"], [
        [/current/i, "current_password"],
        [/password/i, "new_password"],
      ]),
  });
  return (
    <form className="stack" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
      <h3>Change your password</h3>
      <TextField label="Current password" type="password" autoComplete="current-password" error={errors.current_password?.message} {...register("current_password")} />
      <div className="form-grid">
        <TextField label="New password" type="password" autoComplete="new-password" help="At least 8 characters. Avoid well-known ones like password1." error={errors.new_password?.message} {...register("new_password")} />
        <TextField label="Type it again" type="password" autoComplete="new-password" error={errors.confirm?.message} {...register("confirm")} />
      </div>
      {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
      <div>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Change password
        </Button>
      </div>
    </form>
  );
}

function LoginSwitch() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirmOff, setConfirmOff] = useState(false);
  const settings = useQuery({
    queryKey: ["auth-settings"],
    queryFn: () => api.get<{ auth_enabled: boolean }>("/auth/settings"),
  });
  const save = useMutation({
    mutationFn: (on: boolean) => api.put("/auth/settings", { auth_enabled: on }),
    onSuccess: async (_d, on) => {
      await queryClient.invalidateQueries({ queryKey: ["auth-settings"] });
      await queryClient.invalidateQueries({ queryKey: AUTH_KEY });
      toast({ tone: "success", title: on ? "Sign-in is on" : "Sign-in is off" });
    },
  });
  if (settings.isLoading) return <Loading />;
  if (settings.isError) return <ErrorNotice error={settings.error} />;
  return (
    <>
      <SwitchRow
        label="Ask for a password"
        description="When this is off, anyone on your network can open Prerolls Max and change it."
        checked={Boolean(settings.data?.auth_enabled)}
        disabled={save.isPending}
        onChange={(on) => (on ? save.mutate(true) : setConfirmOff(true))}
      />
      {save.isError && <ErrorNotice error={save.error} />}
      <ConfirmDialog
        open={confirmOff}
        onOpenChange={setConfirmOff}
        title="Turn off sign-in?"
        body={<p>Anyone who can reach Prerolls Max on your network could change or delete your intros. Only do this on a network you trust.</p>}
        confirmLabel="Turn off sign-in"
        danger
        onConfirm={() => save.mutateAsync(false)}
      />
    </>
  );
}

export function AccountSection() {
  const { status, isAdmin } = useAuth();
  const signedIn = Boolean(status?.authenticated && status.user);
  return (
    <div className="stack">
      {signedIn && (
        <p>
          Signed in as <strong>{status?.user?.display_name || status?.user?.username}</strong>
          {status?.user?.role === "admin" ? " (admin)" : ""}.
        </p>
      )}
      {isAdmin && <LoginSwitch />}
      {signedIn && (
        <>
          <hr className="divider" />
          <ChangePassword />
        </>
      )}
      {isAdmin && (
        <>
          <hr className="divider" />
          <UsersSection />
        </>
      )}
    </div>
  );
}
