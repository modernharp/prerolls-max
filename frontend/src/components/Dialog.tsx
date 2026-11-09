// Modal dialogs, a confirmation dialog and a side panel, built on Radix
// Dialog so focus is trapped and Escape closes them.
import * as RDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { ErrorNotice } from "./Notice";
import { Button } from "./Button";

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}

const FIELDS = "input:not([type=hidden]):not([type=file]):not([disabled]), textarea:not([disabled]), select:not([disabled]), [role=combobox]";

/**
 * Keyboard focus for dialogs opened from state rather than a Radix trigger:
 * start in the first field (not on the Close button), and go back to the
 * button that opened it when it closes (Radix only does that for its own trigger).
 */
function useDialogFocus(open: boolean) {
  const opener = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  if (open && !wasOpen.current && typeof document !== "undefined") {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  wasOpen.current = open;
  return {
    onOpenAutoFocus: (event: Event) => {
      const content = event.currentTarget as HTMLElement | null;
      const field = [...(content?.querySelectorAll<HTMLElement>(FIELDS) ?? [])].find((el) => !el.closest("[hidden], .visually-hidden"));
      if (field) {
        event.preventDefault();
        field.focus();
      }
    },
    onCloseAutoFocus: (event: Event) => {
      const back = opener.current;
      if (back && back.isConnected && back !== document.body) {
        event.preventDefault();
        back.focus();
      }
    },
  };
}

export function Modal({ open, onOpenChange, title, description, children, footer, wide }: ModalProps) {
  const focus = useDialogFocus(open);
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="overlay" />
        <RDialog.Content className={`dialog ${wide ? "dialog-wide" : ""}`} {...focus}>
          <div className="dialog-header">
            <div>
              <RDialog.Title asChild>
                <h2>{title}</h2>
              </RDialog.Title>
              {description ? (
                <RDialog.Description className="muted dialog-desc">
                  {description}
                </RDialog.Description>
              ) : (
                <RDialog.Description className="visually-hidden">{title}</RDialog.Description>
              )}
            </div>
            <RDialog.Close asChild>
              <button type="button" className="btn btn-ghost btn-icon" aria-label="Close">
                <X size={20} aria-hidden="true" />
              </button>
            </RDialog.Close>
          </div>
          {children}
          {footer && <div className="dialog-footer">{footer}</div>}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

interface ConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  body?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<unknown> | void;
}

export function ConfirmDialog({ open, onOpenChange, title, body, confirmLabel, danger, onConfirm }: ConfirmProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const close = (next: boolean) => {
    if (busy) return;
    if (!next) setError(null);
    onOpenChange(next);
  };
  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onOpenChange={close}
      title={title}
      footer={
        <>
          <Button onClick={() => close(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={confirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {body && <div className="stack-sm">{body}</div>}
      {error ? <ErrorNotice error={error} /> : null}
    </Modal>
  );
}

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  children: ReactNode;
}

export function Sheet({ open, onOpenChange, title, children }: SheetProps) {
  const { onCloseAutoFocus } = useDialogFocus(open);
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="overlay" />
        <RDialog.Content className="sheet" onCloseAutoFocus={onCloseAutoFocus}>
          <div className="dialog-header">
            <RDialog.Title asChild>
              <h2>{title}</h2>
            </RDialog.Title>
            <RDialog.Description className="visually-hidden">Help</RDialog.Description>
            <RDialog.Close asChild>
              <button type="button" className="btn btn-ghost btn-icon" aria-label="Close help">
                <X size={20} aria-hidden="true" />
              </button>
            </RDialog.Close>
          </div>
          {children}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}
