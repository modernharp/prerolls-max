// Labelled form fields. Every field links its label, help text and error
// message to the control (htmlFor, aria-describedby, aria-invalid), and shows
// the error next to the field, not in a pop-up.
import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { AlertCircle } from "lucide-react";
import { isApiError } from "../lib/errors";

interface FieldIds {
  id: string;
  describedBy: string | undefined;
  invalid: boolean;
}

interface FieldShellProps {
  label: ReactNode;
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  id?: string;
  /** Render a group (radio buttons, chips) with a fieldset/legend instead of a label. */
  group?: boolean;
  children: (ids: FieldIds) => ReactNode;
}

export function FieldShell({ label, help, error, optional, id, group, children }: FieldShellProps) {
  const auto = useId();
  const fieldId = id ?? `f${auto.replace(/:/g, "")}`;
  const helpId = help ? `${fieldId}-help` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;
  const labelContent = (
    <>
      {label}
      {optional && <span className="field-optional"> (optional)</span>}
    </>
  );
  const body = (
    <>
      {help && (
        <p id={helpId} className="field-help">
          {help}
        </p>
      )}
      {children({ id: fieldId, describedBy, invalid: Boolean(error) })}
      {error && (
        <p id={errorId} className="field-error">
          <AlertCircle size={16} aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </>
  );
  if (group) {
    return (
      <fieldset className="field plain-fieldset" aria-describedby={describedBy}>
        <legend className="field-label">
          {labelContent}
        </legend>
        {body}
      </fieldset>
    );
  }
  return (
    <div className="field">
      <label className="field-label" htmlFor={fieldId}>
        {labelContent}
      </label>
      {body}
    </div>
  );
}

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "children"> & {
  label: ReactNode;
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  ref?: React.Ref<HTMLInputElement>;
};

export function TextField({ label, help, error, optional, id, className, ...input }: TextFieldProps) {
  return (
    <FieldShell label={label} help={help} error={error} optional={optional} id={id}>
      {(ids) => (
        <input
          {...input}
          id={ids.id}
          className={`input ${className ?? ""}`}
          aria-invalid={ids.invalid || undefined}
          aria-describedby={ids.describedBy}
        />
      )}
    </FieldShell>
  );
}

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "children"> & {
  label: ReactNode;
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  ref?: React.Ref<HTMLTextAreaElement>;
};

export function TextArea({ label, help, error, optional, id, className, ...input }: TextAreaProps) {
  return (
    <FieldShell label={label} help={help} error={error} optional={optional} id={id}>
      {(ids) => (
        <textarea
          {...input}
          id={ids.id}
          className={`textarea ${className ?? ""}`}
          aria-invalid={ids.invalid || undefined}
          aria-describedby={ids.describedBy}
        />
      )}
    </FieldShell>
  );
}

/**
 * Puts the server's field messages (ApiError.fields) next to the fields of a
 * React Hook Form. Older endpoints send one sentence instead; `guess` maps a
 * word in it to a field ([/password/i, "password"]). Returns true when the
 * error is now shown on a field.
 */
export function applyServerFields(
  error: unknown,
  setError: (name: never, error: { type: string; message: string }) => void,
  known: readonly string[],
  guess: [RegExp, string][] = [],
): boolean {
  if (!isApiError(error)) return false;
  let applied = false;
  for (const [name, message] of Object.entries(error.fields)) {
    const field = name.split(".").pop() ?? name;
    if (known.includes(field)) {
      setError(field as never, { type: "server", message });
      applied = true;
    }
  }
  if (!applied && error.status >= 400 && error.status < 500) {
    const hit = guess.find(([pattern]) => pattern.test(error.message));
    if (hit) {
      setError(hit[1] as never, { type: "server", message: error.message });
      applied = true;
    }
  }
  return applied;
}
