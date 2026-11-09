// Logs: newest first, filter by level, search, and look up an error code.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { api } from "../../../lib/api";
import { formatDateTime } from "../../../lib/format";
import type { LogEntry } from "../../../lib/types";
import { Select } from "../../../components/Select";
import { Button } from "../../../components/Button";
import { EmptyState, ErrorNotice, Loading } from "../../../components/Notice";

const LEVELS = [
  { value: "all", label: "Everything" },
  { value: "ERROR", label: "Errors only" },
  { value: "WARNING", label: "Warnings" },
  { value: "INFO", label: "Information" },
];

export function LogsPage() {
  const [level, setLevel] = useState("all");
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [limit, setLimit] = useState(100);
  const logs = useQuery({
    queryKey: ["logs", level, applied, limit],
    queryFn: () =>
      api.get<{ logs: LogEntry[]; total: number }>("/logs", {
        limit,
        level: level === "all" ? undefined : level,
        search: applied || undefined,
        include_reads: false,
      }),
    refetchInterval: 30_000,
  });

  return (
    <div className="stack">
      <p className="muted">
        If Help asks for an error code, type it in the search box to find what happened.
      </p>
      <form
        className="toolbar"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(search.trim());
        }}
      >
        <div className="field grow search-field">
          <label htmlFor="log-search" className="visually-hidden">Search the logs</label>
          <Search size={18} className="search-icon" aria-hidden="true" />
          <input id="log-search" className="input search-input" type="search" placeholder="Search, or paste an error code" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="toolbar-select">
          <Select label={<span className="visually-hidden">Show</span>} value={level} onChange={setLevel} options={LEVELS} />
        </div>
        <Button type="submit">Search</Button>
        <a className="btn" href="/logs/export?format=json" download="prerolls-max-logs.json">
          <Download size={18} aria-hidden="true" /> Download
        </a>
      </form>
      {logs.isLoading ? (
        <Loading />
      ) : logs.isError ? (
        <ErrorNotice error={logs.error} onRetry={() => logs.refetch()} />
      ) : !logs.data?.logs.length ? (
        <EmptyState title="Nothing logged">{applied ? "Nothing matches that search." : "Nothing has been logged yet."}</EmptyState>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table log-table">
              <caption className="visually-hidden">Log entries, newest first</caption>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Level</th>
                  <th scope="col">What happened</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.logs.map((l) => (
                  <tr key={l.id}>
                    <td className="nowrap">{formatDateTime(l.timestamp)}</td>
                    <td>
                      <span className={`badge ${l.level === "ERROR" ? "badge-danger" : l.level === "WARNING" ? "badge-warning" : ""}`}>{l.level.toLowerCase()}</span>
                    </td>
                    <td className="log-message">
                      {l.message}
                      {l.request_id && <div className="muted small">Code {l.request_id}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {logs.data.total > logs.data.logs.length && (
            <div>
              <Button onClick={() => setLimit((n) => n + 200)}>Show older entries</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
