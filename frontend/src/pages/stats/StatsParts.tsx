// Pieces of the What played page: counts as labelled bars, play lists.
import { SERVER_NAMES, type ServerType } from "../../lib/capabilities";
import { formatDateTime, plural } from "../../lib/format";
import { timeAgo, type Count, type Play, type TopItem } from "../../lib/stats";

export const serverName = (s: string | null | undefined) => (s && s in SERVER_NAMES ? SERVER_NAMES[s as ServerType] : s || "Unknown");

/** One measure, one hue: a bar per name with its number written next to it. */
export function CountBars({ title, counts, rename }: { title: string; counts: Count[]; rename?: (name: string) => string }) {
  const top = Math.max(1, ...counts.map((c) => c.plays));
  return (
    <section className="card stat-card" aria-label={title}>
      <h3 className="h4-like">{title}</h3>
      {!counts.length ? (
        <p className="muted small">Nothing yet.</p>
      ) : (
        <ul className="bar-list">
          {counts.slice(0, 8).map((c) => (
            <li key={c.name}>
              <span className="bar-label">{rename ? rename(c.name) : c.name}</span>
              <span className="bar-track" aria-hidden="true">
                <span className="bar-fill" style={{ width: `${(100 * c.plays) / top}%` }} />
              </span>
              <span className="bar-value">{c.plays}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function TopList({ title, items, empty }: { title: string; items: TopItem[]; empty: string }) {
  return (
    <section className="card stat-card" aria-label={title}>
      <h3 className="h4-like">{title}</h3>
      {!items.length ? (
        <p className="muted small">{empty}</p>
      ) : (
        <ol className="rank-list">
          {items.map((t) => (
            <li key={t.preroll_id}>
              <span className="grow">{t.name}</span>
              <span className="muted small nowrap">
                {plural(t.plays, "play")}
                {t.last_played ? `, last ${timeAgo(t.last_played)}` : ""}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function PlaysTable({ plays }: { plays: Play[] }) {
  return (
    <div className="table-wrap">
      <table className="table plays-table">
        <caption className="visually-hidden">Recent plays, newest first</caption>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Intro</th>
            <th scope="col">Before</th>
            <th scope="col">Who and where</th>
          </tr>
        </thead>
        <tbody>
          {plays.map((p) => (
            <tr key={p.id}>
              <td className="nowrap" title={formatDateTime(p.played_at)}>
                {timeAgo(p.played_at)}
              </td>
              <td>
                {p.name}
                {p.rule_name && <div className="muted small">Rule: {p.rule_name}</div>}
              </td>
              <td>{p.item_name || <span className="muted">Not known</span>}</td>
              <td>
                {p.user_name || "Someone"}
                <div className="muted small">
                  {[serverName(p.server_type), p.client, p.device].filter(Boolean).join(" · ")}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
