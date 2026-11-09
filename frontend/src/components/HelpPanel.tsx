// The "?" on every page opens the matching Help article in a side panel,
// so people don't lose their place.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { Sheet } from "./Dialog";
import { Markdown, sectionId } from "./Markdown";
import { getArticle } from "../help";

const HelpContext = createContext<(slug: string) => void>(() => undefined);

export function HelpPanelProvider({ children }: { children: ReactNode }) {
  // "settings#api-keys" opens the Settings article at its "API keys" section.
  const [slug, setSlug] = useState<string | null>(null);
  const open = useCallback((next: string) => setSlug(next), []);
  const [base, section] = (slug ?? "").split("#");
  const article = base ? getArticle(base) : undefined;
  useEffect(() => {
    if (!section || !article) return;
    const timer = window.setTimeout(() => {
      const heading = document.getElementById(sectionId(section));
      heading?.scrollIntoView({ block: "start" });
      heading?.focus({ preventScroll: true });
    }, 50);
    return () => window.clearTimeout(timer);
  }, [section, article]);
  return (
    <HelpContext.Provider value={open}>
      {children}
      <Sheet open={Boolean(slug)} onOpenChange={(o) => !o && setSlug(null)} title={article?.title ?? "Help"}>
        {article ? (
          <div className="stack">
            <Markdown source={article.body} onNavigate={() => setSlug(null)} />
            <hr className="divider" />
            <Link to="/help" onClick={() => setSlug(null)}>
              Browse all help
            </Link>
          </div>
        ) : (
          <p>That help page is missing. Open Help from the menu to search all articles.</p>
        )}
      </Sheet>
    </HelpContext.Provider>
  );
}

export function useOpenHelp() {
  return useContext(HelpContext);
}

export function HelpButton({ slug, label = "Help for this page" }: { slug: string; label?: string }) {
  const open = useOpenHelp();
  return (
    <button type="button" className="btn btn-ghost btn-icon" aria-label={label} title={label} onClick={() => open(slug)}>
      <HelpCircle size={22} aria-hidden="true" />
    </button>
  );
}

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  helpSlug?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, description, helpSlug, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="grow">
        <div className="row title-row">
          <h1>{title}</h1>
          {helpSlug && <HelpButton slug={helpSlug} />}
        </div>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
