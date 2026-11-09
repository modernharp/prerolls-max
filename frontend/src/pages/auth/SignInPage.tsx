import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { signIn, useAuth } from "../../lib/auth";
import { TextField } from "../../components/Field";
import { Button } from "../../components/Button";
import { ErrorNotice, Notice } from "../../components/Notice";
import { Logo } from "../../components/Layout";
import { isApiError } from "../../lib/errors";
import { api } from "../../lib/api";
import { zChecked } from "../../lib/schemas";
import { checkPassword } from "../../lib/validate";
import { useToast } from "../../components/Toast";

const schema = z.object({
  username: z.string().trim().min(1, "Enter your user name."),
  password: z.string().min(1, "Enter your password."),
  remember: z.boolean(),
});

type Values = z.infer<typeof schema>;

export function SignInPage() {
  const { refresh } = useAuth();
  const [error, setError] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), mode: "onTouched", defaultValues: { remember: true } });

  const onSubmit = async (values: Values) => {
    setError(null);
    try {
      await signIn(values.username.toLowerCase(), values.password, values.remember);
      await refresh();
    } catch (e) {
      setError(e);
    }
  };

  const wrongPassword = isApiError(error) && error.status === 401;

  return (
    <div className="auth-screen">
      <div className="card auth-card">
        <div className="brand">
          <Logo size={40} />
          Prerolls Max
        </div>
        <h1>Sign in</h1>
        <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
          <TextField
            label="User name"
            autoComplete="username"
            autoCapitalize="none"
            error={errors.username?.message}
            {...register("username")}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <label className="checkbox">
            <input type="checkbox" {...register("remember")} />
            Keep me signed in on this device
          </label>
          {wrongPassword ? (
            <Notice tone="error" title="That user name and password don't match.">
              Check the spelling. Capital letters count in passwords.
            </Notice>
          ) : error ? (
            <ErrorNotice error={error} />
          ) : null}
          <Button type="submit" variant="primary" block loading={isSubmitting}>
            Sign in
          </Button>
        </form>
        <ForgotPassword />
      </div>
    </div>
  );
}

const resetSchema = z.object({ new_password: zChecked(checkPassword) });

function ForgotPassword() {
  const { status } = useAuth();
  const toast = useToast();
  const [error, setError] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<z.input<typeof resetSchema>, unknown, z.output<typeof resetSchema>>({
    resolver: zodResolver(resetSchema),
    mode: "onTouched",
  });

  const onSubmit = async (values: z.output<typeof resetSchema>) => {
    setError(null);
    try {
      const res = await api.post<{ username: string }>("/auth/reset-password", values, { quietAuth: true });
      reset();
      toast({ tone: "success", title: "Password changed", description: `Sign in as ${res.username} with the new password.` });
    } catch (e) {
      setError(e);
    }
  };

  return (
    <details className="details-toggle">
      <summary>Forgot your password?</summary>
      {status?.is_local ? (
        <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
          <p className="muted small">
            You're on the computer that runs Prerolls Max, so you can set a new password for the admin account here.
          </p>
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            help="At least 8 characters. Avoid well-known ones like password1."
            error={errors.new_password?.message}
            {...register("new_password")}
          />
          {error ? <ErrorNotice error={error} /> : null}
          <Button type="submit" loading={isSubmitting}>
            Set new password
          </Button>
        </form>
      ) : (
        <p className="muted small">
          For safety, the password can only be reset on the computer that runs Prerolls Max. Open Prerolls Max there
          using the address http://localhost with its port number (for example http://localhost:9393), then choose
          "Forgot your password?" again.
        </p>
      )}
    </details>
  );
}
