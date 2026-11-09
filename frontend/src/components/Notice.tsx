// Inline messages: information, warnings, success, and errors with a plain
// message, what to do, and a "Details" section holding the request id.
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { describeError } from "../lib/errors";
import { Button } from "./Button";

type Tone = "info" | "warning" | "success" | "error";

const ICONS = { info: Info, warning: AlertTriangle, success: CheckCircle2, error: AlertCircle };

export function Notice({ tone = "info", title, children, action }: { tone?: Tone; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const Icon = ICONS[tone];
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : undefined}>
      <Icon size={20} aria-hidden="true" />
      <div className="grow">
        {title && <p className="notice-title">{title}</p>}
        {children && <div>{children}</div>}
        {action && <div className="notice-action">{action}</div>}
      </div>
    </div>
  );
}

export function ErrorNotice({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const { message, hint, requestId } = describeError(error);
  return (
    <Notice
      tone="error"
      title={title ?? message}
      action={onRetry ? <Button size="sm" onClick={onRetry}>Try again</Button> : undefined}
    >
      {title && <p>{message}</p>}
      {hint && <p>{hint}</p>}
      {requestId && (
        <details className="details-toggle">
          <summary>Details for a bug report</summary>
          <p>
            Error code: <code>{requestId}</code>. Quote it in Help, Report a problem.
          </p>
        </details>
      )}
    </Notice>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Loader2 size={20} className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon" aria-hidden="true">{icon}</div>}
      <h3 className="empty-title">{title}</h3>
      {children && <p className="empty-text">{children}</p>}
      {action}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}
