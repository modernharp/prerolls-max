// A month at a time: what plays each day, with overlaps marked. Pick a day
// to see which schedule wins and why.
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { MONTH_NAMES } from "../../lib/format";
import { isoDay, monthGrid, planFor, scheduleColour } from "../../lib/calendar";
import { describeSchedule } from "../../lib/scheduleText";
import type { Schedule } from "../../lib/types";
import { IconButton, Button } from "../../components/Button";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const LONG_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type NameOf = (s: Schedule) => string | undefined;

function DayDetail({ date, schedules, playlistName }: { date: Date; schedules: Schedule[]; playlistName?: NameOf }) {
  const plan = planFor(schedules, date);
  const label = date.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return (
    <section className="card day-detail" aria-live="polite" aria-labelledby="day-title">
      <h3 id="day-title">{label}</h3>
      {!plan.on.length ? (
        <p className="muted">No schedule is on. Your default intros play, if they're turned on.</p>
      ) : (
        <ul className="plain-list">
          {plan.on.map((s) => {
            const plays = plan.playing.includes(s);
            return (
              <li key={s.id} className="row">
                <span className="cal-chip" style={{ "--chip": scheduleColour(s) } as React.CSSProperties}>
                  {s.name}
                </span>
                <span className={plays ? "badge badge-success" : "badge"}>{plays ? "Plays" : "Doesn't play"}</span>
                <span className="muted small">{describeSchedule(s, undefined, playlistName?.(s))}</span>
              </li>
            );
          })}
        </ul>
      )}
      {plan.why && <p className="small">{plan.why}</p>}
    </section>
  );
}

export function CalendarView({ schedules, playlistName }: { schedules: Schedule[]; playlistName?: NameOf }) {
  const today = new Date();
  const [cursor, setCursor] = useState({ year: today.getFullYear(), month: today.getMonth() + 1 });
  const [picked, setPicked] = useState<Date>(today);
  const weeks = useMemo(() => monthGrid(cursor.year, cursor.month), [cursor]);
  const shift = (delta: number) =>
    setCursor(({ year, month }) => {
      const d = new Date(year, month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });
  const todayIso = isoDay(today);
  const overlaps = weeks.flat().filter((d) => d.getMonth() === cursor.month - 1 && planFor(schedules, d).on.length > 1).length;

  return (
    <div>
      <div className="cal-head">
        <IconButton label="Previous month" onClick={() => shift(-1)}>
          <ChevronLeft size={20} aria-hidden="true" />
        </IconButton>
        <h3 aria-live="polite">
          {MONTH_NAMES[cursor.month - 1]} {cursor.year}
        </h3>
        <IconButton label="Next month" onClick={() => shift(1)}>
          <ChevronRight size={20} aria-hidden="true" />
        </IconButton>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setCursor({ year: today.getFullYear(), month: today.getMonth() + 1 });
            setPicked(today);
          }}
        >
          Today
        </Button>
        {overlaps > 0 && <span className="badge badge-warning">{overlaps === 1 ? "1 day with overlaps" : `${overlaps} days with overlaps`}</span>}
      </div>
      <table className="calendar">
        <caption className="visually-hidden">
          Schedules in {MONTH_NAMES[cursor.month - 1]} {cursor.year}. Pick a day to see what plays.
        </caption>
        <thead>
          <tr>
            {DAYS.map((d, i) => (
              <th key={d} scope="col" abbr={LONG_DAYS[i]}>
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={isoDay(week[0]!)}>
              {week.map((day) => {
                const plan = planFor(schedules, day);
                const iso = isoDay(day);
                const other = day.getMonth() !== cursor.month - 1;
                const label = `${day.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}: ${
                  plan.on.length ? plan.on.map((s) => `${s.name}${plan.playing.includes(s) ? "" : " (doesn't play)"}`).join(", ") : "default intros"
                }`;
                return (
                  <td key={iso}>
                    <button
                      type="button"
                      className={`cal-day ${other ? "other" : ""} ${iso === todayIso ? "today" : ""} ${plan.on.length > 1 ? "overlap" : ""}`}
                      aria-pressed={isoDay(picked) === iso}
                      aria-label={label}
                      onClick={() => setPicked(day)}
                    >
                      <span className="cal-num">{day.getDate()}</span>
                      {plan.on.slice(0, 3).map((s) => (
                        <span
                          key={s.id}
                          className={`cal-chip ${plan.playing.includes(s) ? "" : "loses"}`}
                          style={{ "--chip": scheduleColour(s) } as React.CSSProperties}
                          aria-hidden="true"
                        >
                          {s.name}
                        </span>
                      ))}
                      {plan.on.length > 3 && (
                        <span className="cal-more" aria-hidden="true">
                          +{plan.on.length - 3} more
                        </span>
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="cal-legend" aria-hidden="true">
        <span>
          <span className="cal-swatch" />
          Two or more schedules on that day
        </span>
        <span>Crossed out: on, but another schedule wins</span>
      </div>
      <DayDetail date={picked} schedules={schedules} playlistName={playlistName} />
    </div>
  );
}
