// First run: create the admin account, then go to the setup guide.
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { createFirstAccount, useAuth } from "../../lib/auth";
import { confirmPassword, withConfirm, zChecked } from "../../lib/schemas";
import { checkPassword, cleanName, cleanUsername } from "../../lib/validate";
import { TextField, applyServerFields } from "../../components/Field";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/Notice";
import { Logo } from "../../components/Layout";

const schema = z
  .object({
    username: zChecked(cleanUsername),
    display_name: z.string().transform((v, ctx) => {
      if (!v.trim()) return "";
      const r = cleanName(v, { what: "name", maxLen: 60 });
      if (!r.ok) {
        ctx.addIssue({ code: "custom", message: r.message });
        return z.NEVER;
      }
      return r.value;
    }),
    password: zChecked(checkPassword),
    confirm: z.string(),
  })
  .superRefine((v, ctx) => confirmPassword(v.password, v.confirm, ctx));

type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

export function SetupPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    setError: setFieldError,
    formState: { errors, isSubmitting },
  } = useForm<Input, unknown, Output>({ resolver: withConfirm(zodResolver(schema), "password"), mode: "onTouched" });

  const onSubmit = async (values: Output) => {
    setError(null);
    try {
      await createFirstAccount({
        username: values.username,
        password: values.password,
        display_name: values.display_name || undefined,
      });
      navigate("/welcome");
      await refresh();
    } catch (e) {
      const known = ["username", "password", "display_name"] as const;
      if (applyServerFields(e, setFieldError, known, [[/password/i, "password"], [/user ?name/i, "username"]])) return;
      setError(e);
    }
  };

  return (
    <div className="auth-screen">
      <div className="card auth-card">
        <div className="brand">
          <Logo size={40} />
          Prerolls Max
        </div>
        <h1>Welcome</h1>
        <p className="muted">
          First, make an account to sign in with. It keeps other people on your network from changing your intros.
        </p>
        <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
          <TextField
            label="User name"
            autoComplete="username"
            autoCapitalize="none"
            help="Letters and numbers. Dots, dashes and underscores are fine too."
            error={errors.username?.message}
            {...register("username")}
          />
          <TextField
            label="Your name"
            optional
            autoComplete="name"
            help="Shown in the menu. Leave blank to use your user name."
            error={errors.display_name?.message}
            {...register("display_name")}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="new-password"
            help="At least 8 characters. A short sentence is easy to remember and hard to guess."
            error={errors.password?.message}
            {...register("password")}
          />
          <TextField
            label="Type the password again"
            type="password"
            autoComplete="new-password"
            error={errors.confirm?.message}
            {...register("confirm")}
          />
          {error ? <ErrorNotice error={error} /> : null}
          <Button type="submit" variant="primary" block loading={isSubmitting}>
            Create account
          </Button>
        </form>
      </div>
    </div>
  );
}
