// Short messages after an action ("Saved", "Deleted. Undo"). Never alert().
import * as RToast from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { X } from "lucide-react";

type Tone = "info" | "success" | "error";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: Tone;
  action?: { label: string; onClick: () => void };
  /** Milliseconds. Undo toasts stay longer. */
  duration?: number;
}

interface ToastItem extends ToastInput {
  id: number;
  open: boolean;
}

const ToastContext = createContext<(t: ToastInput) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: ToastInput) => {
    setItems((list) => [...list.slice(-3), { ...t, id: Date.now() + Math.random(), open: true }]);
  }, []);
  const close = (id: number) => setItems((list) => list.map((t) => (t.id === id ? { ...t, open: false } : t)));
  const remove = (id: number) => setItems((list) => list.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={push}>
      <RToast.Provider swipeDirection="right" label="Messages">
        {children}
        {items.map((t) => (
          <RToast.Root
            key={t.id}
            open={t.open}
            onOpenChange={(open) => {
              if (!open) {
                close(t.id);
                window.setTimeout(() => remove(t.id), 300);
              }
            }}
            duration={t.duration ?? (t.action ? 10_000 : 5_000)}
            className={`toast toast-${t.tone ?? "info"}`}
            type={t.tone === "error" ? "foreground" : "background"}
          >
            <div className="grow">
              <RToast.Title className="toast-title">{t.title}</RToast.Title>
              {t.description && <RToast.Description className="toast-desc">{t.description}</RToast.Description>}
            </div>
            {t.action && (
              <RToast.Action altText={t.action.label} asChild>
                <button type="button" className="btn btn-sm" onClick={t.action.onClick}>
                  {t.action.label}
                </button>
              </RToast.Action>
            )}
            <RToast.Close className="btn btn-ghost btn-sm btn-icon" aria-label="Dismiss">
              <X size={16} aria-hidden="true" />
            </RToast.Close>
          </RToast.Root>
        ))}
        <RToast.Viewport className="toast-viewport" />
      </RToast.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
