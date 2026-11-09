// "Did the intros actually play?" From GET /api/health/intros: playbacks in
// the last week that started without intros, why, and what to change.
import { AlertTriangle, CheckCircle2, Info, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import { plural } from "../../lib/format";
import { timeAgo, useIntroHealth, type HealthWarning } from "../../lib/stats";
import { ErrorNotice, Loading } from "../../components/Notice";
import { serverName } from "../stats/StatsParts";

function WarningCard({ w }: { w: HealthWarning }) {
  const Icon = w.severity === "warning" ? AlertTriangle : Info;
  return (
    <li className={`card health-card ${w.severity}`}>
      <div className="health-head">
        <Icon size={22} className={w.severity === "warning" ? "status-warn" : "muted"} aria-hidden="true" />
        <h3 className="h4-like grow">{w.title}</h3>
        {w.server && <span className="badge">{serverName(w.server)}</span>}
      </div>
      <p>{w.reason}</p>
      <p className="health-fix">
        <Wrench size={16} aria-hidden="true" />
        <span>
          <strong>How to fix it: </strong>
          {w.fix}
        </span>
      </p>
      {(w.examples.length > 0 || w.last_seen) && (
        <details className="details-toggle">
          <summary>
            {w.last_seen ? `Last seen ${timeAgo(w.last_seen)}` : "Details"}
            {w.examples.length ? `, ${plural(w.examples.length, "example")}` : ""}
          </summary>
          <ul className="plain-list small">
            {w.examples.map((e, i) => (
              <li key={i}>
                {e.title || "Something"}
                <span className="muted">
                  {" "}
                  {[e.user, e.device, timeAgo(e.at)].filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

export function IntroHealth() {
  const health = useIntroHealth();
  if (health.isLoading) return <Loading label="Checking recent playbacks…" />;
  if (health.isError) return <ErrorNotice error={health.error} title="Couldn't check recent playbacks" onRetry={() => health.refetch()} />;
  const h = health.data;
  if (!h) return null;
  const ok = h.status === "ok";
  return (
    <div className="stack">
      <div className={`status-row ${ok ? "ok" : h.status === "warning" ? "bad" : ""}`}>
        {ok ? <CheckCircle2 size={24} className="status-ok" aria-hidden="true" /> : h.status === "warning" ? <AlertTriangle size={24} className="status-warn" aria-hidden="true" /> : <Info size={24} className="muted" aria-hidden="true" />}
        <div className="grow">
          <strong>Intros in the last {h.days} days</strong>
          <div className="muted small">
            {h.message}
            {h.playbacks > 0 && ` ${h.with_intros} of ${plural(h.playbacks, "playback")} had their intros.`}
          </div>
        </div>
        <Link to="/played" className="small nowrap">
          What played
        </Link>
      </div>
      {h.warnings.length > 0 && (
        <ul className="health-list">
          {h.warnings.map((w) => (
            <WarningCard key={w.id} w={w} />
          ))}
        </ul>
      )}
    </div>
  );
}
