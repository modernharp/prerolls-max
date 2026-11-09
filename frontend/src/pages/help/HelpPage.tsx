import { useState } from "react";
import { Link } from "react-router-dom";
import { Bug, LifeBuoy, Search } from "lucide-react";
import { ARTICLES, searchHelp, type HelpArticle } from "../../help";
import { PageHeader } from "../../components/HelpPanel";
import { EmptyState } from "../../components/Notice";

const GROUPS: HelpArticle["group"][] = ["Start here", "Intro videos", "When they play", "Media servers", "Advanced", "Reference"];

export default function HelpPage() {
  const [query, setQuery] = useState("");
  const hits = searchHelp(query);
  return (
    <>
      <PageHeader title="Help" description="Guides and answers. Help works even when you're offline." />
      <div className="field search-field section-gap">
        <label htmlFor="help-search" className="visually-hidden">
          Search help
        </label>
        <Search size={18} className="search-icon" aria-hidden="true" />
        <input
          id="help-search"
          className="input search-input"
          type="search"
          placeholder="Search help, like 'Apple TV' or 'Docker'"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {query.trim().length > 1 ? (
        <section aria-live="polite" aria-label="Search results">
          {hits.length ? (
            <ul className="list">
              {hits.map(({ article, snippet }) => (
                <li key={article.slug} className="list-row">
                  <div className="grow">
                    <Link to={`/help/${article.slug}`}>
                      <strong>{article.title}</strong>
                    </Link>
                    <div className="muted small">{snippet}</div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No help pages match">
              Try fewer or different words, or use the troubleshooter below.
            </EmptyState>
          )}
        </section>
      ) : (
        <>
          <div className="card-grid section">
            <Link to="/help/troubleshoot" className="card link-card">
              <LifeBuoy size={28} aria-hidden="true" />
              <strong>My intro isn't playing</strong>
              <span className="muted small">Answer a few questions and get the fix for your server and device.</span>
            </Link>
            <Link to="/help/report" className="card link-card">
              <Bug size={28} aria-hidden="true" />
              <strong>Report a problem</strong>
              <span className="muted small">Tell the developers what went wrong, with the details they need.</span>
            </Link>
          </div>
          {GROUPS.map((group) => (
            <section key={group} className="section" aria-labelledby={`g-${group}`}>
              <h2 id={`g-${group}`}>{group}</h2>
              <ul className="list">
                {ARTICLES.filter((a) => a.group === group).map((a) => (
                  <li key={a.slug} className="list-row">
                    <div className="grow">
                      <Link to={`/help/${a.slug}`}>
                        <strong>{a.title}</strong>
                      </Link>
                      <div className="muted small">{a.summary}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}
    </>
  );
}
