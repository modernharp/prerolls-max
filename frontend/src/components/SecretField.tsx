// Fields for keys and tokens. They start hidden, like a password, so a key
// doesn't end up in a screenshot or a screen share; "Show" reveals it.
// Typing and pasting work as in any field, and the browser is asked not to
// save, autofill or spell-check it.
import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";
import { FieldShell } from "./Field";

/** The Show/Hide button. Its name says what it does now; aria-pressed says the key is showing. */
export function RevealButton({ shown, onToggle, what, controls }: { shown: boolean; onToggle: () => void; what: string; controls?: string }) {
  return (
    <button
      type="button"
      className="btn btn-sm secret-toggle"
      aria-pressed={shown}
      aria-controls={controls}
      aria-label={`${shown ? "Hide" : "Show"} ${what}`}
      onClick={onToggle}
    >
      {shown ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
      <span aria-hidden="true">{shown ? "Hide" : "Show"}</span>
    </button>
  );
}

type SecretFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "children" | "type"> & {
  label: ReactNode;
  /** What the button shows or hides, in words ("API key"). Defaults to the label when it is text. */
  what?: string;
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  ref?: React.Ref<HTMLInputElement>;
};

export function SecretField({ label, what, help, error, optional, id, className, ...input }: SecretFieldProps) {
  const [shown, setShown] = useState(false);
  const name = what ?? (typeof label === "string" ? label : "key");
  return (
    <FieldShell label={label} help={help} error={error} optional={optional} id={id}>
      {(ids) => (
        <div className="secret-input">
          <input
            autoCapitalize="none"
            autoCorrect="off"
            {...input}
            id={ids.id}
            type={shown ? "text" : "password"}
            autoComplete="off"
            spellCheck={false}
            data-1p-ignore=""
            data-lpignore="true"
            className={`input ${className ?? ""}`}
            aria-invalid={ids.invalid || undefined}
            aria-describedby={ids.describedBy}
          />
          <RevealButton shown={shown} onToggle={() => setShown((s) => !s)} what={name} controls={ids.id} />
        </div>
      )}
    </FieldShell>
  );
}

/** A key shown once (a new API key): hidden until "Show"; copying works either way. */
export function SecretValue({ value, what = "key" }: { value: string; what?: string }) {
  const [shown, setShown] = useState(false);
  const auto = useId();
  const valueId = `secret${auto.replace(/:/g, "")}`;
  return (
    <div className="secret-input">
      <code id={valueId} className="key-box grow" tabIndex={0} aria-label={shown ? undefined : `${what}, hidden`}>
        {shown ? value : "•".repeat(Math.min(Math.max(value.length, 12), 32))}
      </code>
      <RevealButton shown={shown} onToggle={() => setShown((s) => !s)} what={what} controls={valueId} />
    </div>
  );
}
