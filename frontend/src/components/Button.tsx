import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "danger-outline" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "md" | "sm";
  loading?: boolean;
  icon?: ReactNode;
  block?: boolean;
}

export function classes(variant: Variant = "secondary", size: "md" | "sm" = "md", block = false, extra = "") {
  return [
    "btn",
    variant === "primary" && "btn-primary",
    variant === "danger" && "btn-danger",
    variant === "danger-outline" && "btn-danger-outline",
    variant === "ghost" && "btn-ghost",
    size === "sm" && "btn-sm",
    block && "btn-block",
    extra,
  ]
    .filter(Boolean)
    .join(" ");
}

export function Button({ variant, size, loading, icon, block, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={classes(variant, size, block, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 size={18} className="spinner" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}

interface ButtonLinkProps extends LinkProps {
  variant?: Variant;
  size?: "md" | "sm";
  icon?: ReactNode;
}

export function ButtonLink({ variant, size, icon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={classes(variant, size, false, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

export function IconButton({ label, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" className={`btn btn-ghost btn-icon ${className ?? ""}`} aria-label={label} title={label} {...rest}>
      {children}
    </button>
  );
}
