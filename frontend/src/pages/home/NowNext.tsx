// "What plays now and next", from the schedules and the scheduler's view.
import { CalendarClock, PlayCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { useActiveScheduleIds, useCategories, useFiller, useSchedules } from "../../lib/queries";
import { describeSchedule } from "../../lib/scheduleText";
import { pickWinners } from "../../lib/calendar";
import { formatDateTime } from "../../lib/format";
import { ErrorNotice, Loading } from "../../components/Notice";
import type { Schedule } from "../../lib/types";

function nextUp(schedules: Schedule[], activeIds: number[], now = new Date()): Schedule | undefined {
  return schedules
    .filter((s) => s.is_active && !activeIds.includes(s.id) && s.next_run && new Date(s.next_run) >= now)
    .sort((a, b) => (a.next_run ?? "").localeCompare(b.next_run ?? ""))[0];
}

export function NowNext() {
  const schedules = useSchedules();
  const active = useActiveScheduleIds();
  const filler = useFiller();
  const categories = useCategories();

  if (schedules.isLoading || active.isLoading) return <Loading />;
  if (schedules.isError) return <ErrorNotice error={schedules.error} onRetry={() => schedules.refetch()} />;

  const list = schedules.data ?? [];
  const activeIds = active.data ?? [];
  // Several can be on at once; only the winner's intros play (same rules as the calendar).
  const plan = pickWinners(list.filter((s) => activeIds.includes(s.id)));
  const playing = plan.playing;
  const alsoOn = plan.on.filter((s) => !playing.includes(s));
  const next = nextUp(list, activeIds);
  const fillerName = filler.data?.enabled && filler.data.category_id
    ? categories.data?.find((c) => c.id === filler.data?.category_id)?.name
    : undefined;

  return (
    <div className="now-next">
      <div className="now-card">
        <h3 className="row">
          <PlayCircle size={20} aria-hidden="true" /> Playing now
        </h3>
        {playing.length ? (
          <ul className="plain-list">
            {playing.map((s) => (
              <li key={s.id}>
                <strong>{s.name}</strong>
                <div className="muted small">{describeSchedule(s)}</div>
              </li>
            ))}
            {alsoOn.length > 0 && (
              <li className="muted small">
                Also on, but not playing: {alsoOn.map((s) => s.name).join(", ")}. {plan.why}
              </li>
            )}
          </ul>
        ) : fillerName ? (
          <p>
            Your default intros: <strong>{fillerName}</strong>. They play when no schedule is on.
          </p>
        ) : (
          <p className="muted">
            No schedule is on right now, so your media server keeps the last intro it was given.{" "}
            <Link to="/schedules">Set default intros</Link> to fill the gaps.
          </p>
        )}
      </div>
      <div className="now-card">
        <h3 className="row">
          <CalendarClock size={20} aria-hidden="true" /> Coming up
        </h3>
        {next ? (
          <>
            <strong>{next.name}</strong>
            <div className="muted small">Starts {formatDateTime(next.next_run)}</div>
            <div className="muted small">{describeSchedule(next)}</div>
          </>
        ) : (
          <p className="muted">
            Nothing else is scheduled. <Link to="/schedules/new">Choose when intros play</Link>.
          </p>
        )}
      </div>
    </div>
  );
}
