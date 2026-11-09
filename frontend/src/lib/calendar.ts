// Which schedules are on for a given day, and which of them wins, for the
// calendar. Follows the scheduler (scheduler.py _is_schedule_active and the
// overlap rules) at the level of whole days; time-of-day windows are shown
// as text, not split into hours.
import { parsePattern } from "./scheduleDraft";
import type { Schedule } from "./types";

const WEEKDAY_NAMES = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

export function isoDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

const monthDay = (iso: string) => iso.slice(5, 10);

/** Is month-day `md` ("10-31") inside the yearly window start..end, which may wrap past New Year? */
function inYearlyWindow(start: string, end: string, md: string): boolean {
  const s = monthDay(start);
  const e = monthDay(end);
  return s <= e ? md >= s && md <= e : md >= s || md <= e;
}

/** Does the schedule play at some time on this day? */
export function playsOn(s: Schedule, date: Date): boolean {
  if (!s.is_active || !s.start_date || s.recurrence_error) return false;
  const day = isoDay(date);
  const md = monthDay(day);
  const start = s.start_date.slice(0, 10);
  const end = s.end_date?.slice(0, 10) ?? null;

  if (s.type === "yearly" || s.type === "holiday") {
    if (s.holiday_name) {
      // The server keeps start_date on the holiday's next date.
      if (s.type === "holiday" && day < start && Number(day.slice(0, 4)) < Number(start.slice(0, 4))) return false;
      if (md !== monthDay(start)) return false;
    } else if (end) {
      if (!inYearlyWindow(start, end, md)) return false;
    } else if (s.type === "holiday" && md !== monthDay(start)) {
      return false;
    }
  } else {
    if (day < start) return false;
    if (end && day > end) return false;
  }

  const pattern = parsePattern(s);
  if (pattern.weekDays?.length && !pattern.weekDays.map((d) => d.toLowerCase()).includes(WEEKDAY_NAMES[date.getDay()] ?? "")) return false;
  if (pattern.months?.length && !pattern.months.map(Number).includes(date.getMonth() + 1)) return false;
  if (pattern.monthDays?.length && !pattern.monthDays.map(Number).includes(date.getDate())) return false;
  return true;
}

export interface DayPlan {
  /** Every schedule that's on. */
  on: Schedule[];
  /** The ones whose intros actually play. */
  playing: Schedule[];
  /** How the winner was picked, in a sentence. */
  why: string | null;
}

const priority = (s: Schedule) => s.priority ?? 5;

function byPriority(a: Schedule, b: Schedule): number {
  return priority(b) - priority(a) || (a.end_date ?? "9999").localeCompare(b.end_date ?? "9999") || a.id - b.id;
}

/** Same rules as the scheduler: "only these" first, then mixing, then the most important. */
export function planFor(schedules: Schedule[], date: Date): DayPlan {
  return pickWinners(schedules.filter((s) => playsOn(s, date)));
}

/** Of the schedules that are on, which ones play (the Home page uses it for "now"). */
export function pickWinners(schedules: Schedule[]): DayPlan {
  const on = [...schedules].sort(byPriority);
  if (on.length <= 1) return { on, playing: on, why: null };
  const exclusive = on.filter((s) => s.exclusive);
  if (exclusive.length) {
    const winner = exclusive[0]!;
    return { on, playing: [winner], why: `${winner.name} is set to "only these intros", so it's the only one that plays.` };
  }
  const blend = on.filter((s) => s.blend_enabled);
  if (blend.length >= 2) {
    return { on, playing: blend, why: `${blend.map((s) => s.name).join(" and ")} are set to mix, so their intros play together.` };
  }
  const winner = on[0]!;
  return { on, playing: [winner], why: `${winner.name} is the most important (${priority(winner)} out of 10), so it plays.` };
}

/** The weeks shown for a month: Monday first, padded with the days around it. */
export function monthGrid(year: number, month: number): Date[][] {
  const first = new Date(year, month - 1, 1);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(year, month - 1, 1 - offset);
  const weeks: Date[][] = [];
  for (let w = 0; w < 6; w += 1) {
    const week: Date[] = [];
    for (let d = 0; d < 7; d += 1) week.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d));
    if (w > 3 && week[0]!.getMonth() !== month - 1) break;
    weeks.push(week);
  }
  return weeks;
}

/** A stable colour for each schedule, from a small set that reads in light and dark. */
const COLOURS = ["#6366f1", "#d97706", "#059669", "#db2777", "#0891b2", "#7c3aed", "#65a30d", "#dc2626"];
export function scheduleColour(s: Schedule): string {
  if (s.color && /^#[0-9a-f]{6}$/i.test(s.color)) return s.color;
  return COLOURS[s.id % COLOURS.length]!;
}
