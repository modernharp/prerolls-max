// Renders a bundled Help article. Links to other articles ("help:slug") and
// to pages in the app ("app:/servers") stay inside the app; others open in a
// new tab. Section headings get ids ("help-api-keys") so a page's "?" can open
// the article at its own section.
import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router-dom";

function textOf(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) => (typeof child === "string" || typeof child === "number" ? String(child) : isValidElement<{ children?: ReactNode }>(child) ? textOf(child.props.children) : ""))
    .join("");
}

/** "API keys" -> "help-api-keys": the id a section heading gets. */
export const sectionId = (heading: string) =>
  "help-" + heading.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export function Markdown({ source, onNavigate }: { source: string; onNavigate?: () => void }) {
  const components: Components = {
    h2({ children }) {
      return (
        <h2 id={sectionId(textOf(children))} tabIndex={-1}>
          {children}
        </h2>
      );
    },
    h3({ children }) {
      return (
        <h3 id={sectionId(textOf(children))} tabIndex={-1}>
          {children}
        </h3>
      );
    },
    a({ href, children }) {
      if (href?.startsWith("help:")) {
        return (
          <Link to={`/help/${href.slice(5)}`} onClick={onNavigate}>
            {children}
          </Link>
        );
      }
      if (href?.startsWith("app:")) {
        return (
          <Link to={href.slice(4)} onClick={onNavigate}>
            {children}
          </Link>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer noopener">
          {children}
        </a>
      );
    },
    table({ children }) {
      return (
        <div className="table-wrap">
          <table className="table">{children}</table>
        </div>
      );
    },
  };
  return (
    <div className="prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
