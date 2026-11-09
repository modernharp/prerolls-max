// Zod building blocks made from the checks in validate.ts, for React Hook Form.
import { z } from "zod";
import type { FieldValues, Resolver } from "react-hook-form";
import type { Check } from "./validate";

/** A required text field cleaned by `check`. */
export function zChecked(check: (value: string) => Check<string>) {
  return z.string().transform((value, ctx) => {
    const result = check(value);
    if (!result.ok) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: result.message });
      return z.NEVER;
    }
    return result.value;
  });
}

/** Like zChecked, but an empty box is fine and becomes "". */
export function zOptionalChecked(check: (value: string) => Check<string>) {
  return z.string().transform((value, ctx) => {
    if (!value.trim()) return "";
    const result = check(value);
    if (!result.ok) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: result.message });
      return z.NEVER;
    }
    return result.value;
  });
}

/**
 * Adds the "Type the password again" check to a form's resolver. Zod skips a
 * whole-form check while any field has a problem, so on its own "The two
 * passwords don't match" waited until the password was long enough; this
 * compares the two boxes as typed, whatever else needs fixing.
 */
export function withConfirm<T extends FieldValues>(resolver: Resolver<T>, passwordField: string): Resolver<T> {
  return async (values, context, options) => {
    const result = await resolver(values, context, options);
    const raw = values as Record<string, unknown>;
    const confirm = typeof raw.confirm === "string" ? raw.confirm : "";
    const message = !confirm ? "Type the password again." : confirm !== raw[passwordField] ? "The two passwords don't match." : undefined;
    const errors = result.errors as Record<string, unknown>;
    if (!message || errors.confirm) return result;
    return { values: {}, errors: { ...result.errors, confirm: { type: "custom", message } } } as Awaited<ReturnType<Resolver<T>>>;
  };
}

/** "Type the password again": only says they differ once the first one is valid. */
export function confirmPassword(password: unknown, confirm: string, ctx: z.RefinementCtx) {
  if (!confirm) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["confirm"], message: "Type the password again." });
  else if (typeof password === "string" && password !== confirm) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["confirm"], message: "The two passwords don't match." });
  }
}
