// The top of every "When They Play" page: title, tabs, and how Prerolls Max
// decides what plays (never-play list, then rules, schedules, default intros).
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Ban, CalendarClock, ListChecks } from "lucide-react";
import { PageHeader } from "../../components/HelpPanel";

export function WhenHeader({ actions, helpSlug = "schedules" }: { actions?: ReactNode; helpSlug?: string }) {
  return (
    <>
      <PageHeader title="When They Play" description="Choose which intros play, and when." helpSlug={helpSlug} actions={actions} />
      <nav className="tabs-list" aria-label="When they play">
        <NavLink to="/schedules" end className="tab">
          <CalendarClock size={18} aria-hidden="true" /> Schedules
        </NavLink>
        <NavLink to="/schedules/rules" className="tab">
          <ListChecks size={18} aria-hidden="true" /> Rules
        </NavLink>
        <NavLink to="/schedules/never-play" className="tab">
          <Ban size={18} aria-hidden="true" /> Never play
        </NavLink>
      </nav>
    </>
  );
}

const STEPS: { title: string; text: string }[] = [
  { title: "Never-play list", text: "Titles on it never get an intro." },
  { title: "Rules", text: "The first rule that matches the title picks the intros." },
  { title: "Schedules", text: "If no rule matches, the schedule that's on decides." },
  { title: "Default intros", text: "If no schedule is on, these play." },
];

/** "How Prerolls Max picks", as four numbered steps. `current` highlights one. */
export function DecisionOrder({ current }: { current?: number }) {
  return (
    <section className="card decision-order" aria-labelledby="order-title">
      <h2 id="order-title" className="h4-like">How Prerolls Max picks an intro</h2>
      <ol className="decision-steps">
        {STEPS.map((s, i) => (
          <li key={s.title} className={current === i ? "current" : undefined} aria-current={current === i ? "step" : undefined}>
            <span className="order-num" aria-hidden="true">{i + 1}</span>
            <span>
              <strong>{s.title}</strong>
              <span className="muted small"> {s.text}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="muted small">
        Steps 1 and 2 need Jellyfin or Emby with the Prerolls Max Intros plugin. Plex picks its intro before it knows which movie
        starts, so on Plex only schedules and default intros apply.
      </p>
    </section>
  );
}
