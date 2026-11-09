// The "When they play" wizard's answers, and how they become a schedule the
// server understands (and back, for editing).
import type { Schedule } from "./types";
import { sanitizeSequence, type SavedPlaylist } from "./playlist";

export type WhenKind = "yearly" | "dates" | "weekly" | "always" | "holiday" | "monthly" | "specific";
export type Overlap = "only" | "mix" | "priority";

export const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
export type Weekday = (typeof WEEKDAYS)[number];

export interface ScheduleDraft {
  name: string;
  /** A collection, or a playlist (Advanced). */
  source: "collection" | "playlist";
  collectionId: string;
  playlistId: string;
  order: "random" | "in_order";
  when: WhenKind;
  startMonth: number;
  startDay: number;
  endMonth: number;
  endDay: number;
  startDate: string;
  endDate: string;
  weekDays: Weekday[];
  holidayCountry: string;
  holidayName: string;
  /** Days of the month (1-31), for "monthly". */
  monthDays: number[];
  /** Months (1-12) for "monthly"; none means every month. */
  months: number[];
  /** One month and some of its days, every year, for "specific". */
  specificMonth: number;
  specificDays: number[];
  timeLimit: boolean;
  timeStart: string;
  timeEnd: string;
  overlap: Overlap;
  priority: number;
}

export function todayIso(now = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** "US" from a browser language like en-US; "US" when there's no region. */
export function guessCountry(): string {
  const lang = typeof navigator !== "undefined" ? navigator.language : "";
  const region = /[-_]([A-Za-z]{2})$/.exec(lang)?.[1];
  return region ? region.toUpperCase() : "US";
}

export function emptyDraft(now = new Date()): ScheduleDraft {
  return {
    name: "",
    source: "collection",
    collectionId: "",
    playlistId: "",
    order: "random",
    when: "yearly",
    startMonth: 10,
    startDay: 1,
    endMonth: 10,
    endDay: 31,
    startDate: todayIso(now),
    endDate: "",
    weekDays: ["friday", "saturday"],
    holidayCountry: guessCountry(),
    holidayName: "",
    monthDays: [1],
    months: [],
    specificMonth: 12,
    specificDays: [24, 25],
    timeLimit: false,
    timeStart: "18:00",
    timeEnd: "23:59",
    overlap: "priority",
    priority: 5,
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

export interface SchedulePayload {
  name: string;
  type: string;
  start_date: string;
  end_date: string | null;
  category_id: number | null;
  playlist: boolean;
  recurrence_pattern: string | null;
  blend_enabled: boolean;
  exclusive: boolean;
  priority: number;
  sequence: string | null;
  source_sequence_id: number | null;
  holiday_name: string | null;
  holiday_country: string | null;
  is_active?: boolean;
}

export function draftToPayload(draft: ScheduleDraft, now = new Date(), playlists: SavedPlaylist[] = []): SchedulePayload {
  const pattern: Record<string, unknown> = {};
  if (draft.timeLimit) pattern.timeRange = { start: draft.timeStart, end: draft.timeEnd };
  let type = "daily";
  let start = `${todayIso(now)}T00:00`;
  let end: string | null = null;

  switch (draft.when) {
    case "yearly":
      type = "yearly";
      // Yearly schedules are stored in year 2000 and repeat every year.
      start = `2000-${pad(draft.startMonth)}-${pad(draft.startDay)}T00:00`;
      end = `2000-${pad(draft.endMonth)}-${pad(draft.endDay)}T23:59`;
      break;
    case "dates":
      start = `${draft.startDate}T00:00`;
      end = draft.endDate ? `${draft.endDate}T23:59` : null;
      break;
    case "weekly":
      type = "weekly";
      pattern.weekDays = [...draft.weekDays];
      break;
    case "holiday":
      // The server works out the holiday's date for each year.
      type = "holiday";
      break;
    case "monthly":
      type = "monthly";
      start = "2000-01-01T00:00";
      pattern.monthDays = [...draft.monthDays].sort((a, b) => a - b);
      if (draft.months.length && draft.months.length < 12) pattern.months = [...draft.months].sort((a, b) => a - b);
      break;
    case "specific":
      type = "monthly";
      start = "2000-01-01T00:00";
      pattern.months = [draft.specificMonth];
      pattern.monthDays = [...draft.specificDays].sort((a, b) => a - b);
      break;
    case "always":
      break;
  }

  const playlist = draft.source === "playlist" ? playlists.find((p) => String(p.id) === draft.playlistId) : undefined;
  const holiday = draft.when === "holiday";
  return {
    name: draft.name.trim(),
    type,
    start_date: start,
    end_date: end,
    category_id: !playlist && draft.collectionId ? Number(draft.collectionId) : null,
    playlist: !playlist && draft.order === "in_order",
    sequence: playlist ? JSON.stringify(sanitizeSequence(playlist.blocks)) : null,
    source_sequence_id: playlist ? playlist.id : null,
    holiday_name: holiday ? draft.holidayName : null,
    holiday_country: holiday ? draft.holidayCountry : null,
    recurrence_pattern: Object.keys(pattern).length ? JSON.stringify(pattern) : null,
    exclusive: draft.overlap === "only",
    blend_enabled: draft.overlap === "mix",
    priority: draft.priority,
  };
}

export function parsePattern(schedule: Pick<Schedule, "recurrence_pattern">): {
  timeRange?: { start?: string; end?: string };
  weekDays?: string[];
  months?: number[];
  monthDays?: number[];
} {
  try {
    const parsed: unknown = JSON.parse(schedule.recurrence_pattern || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as ReturnType<typeof parsePattern>) : {};
  } catch {
    return {};
  }
}

const datePart = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "");

/** Turns a saved schedule back into wizard answers, or null if the wizard can't show it (a playlist typed in by hand, custom rules). */
export function scheduleToDraft(schedule: Schedule): ScheduleDraft | null {
  if (schedule.sequence && !schedule.source_sequence_id) return null;
  if (!["yearly", "daily", "weekly", "monthly", "holiday"].includes(schedule.type)) return null;
  if (schedule.type === "yearly" && schedule.holiday_name) return null;
  const pattern = parsePattern(schedule);
  const base = emptyDraft();
  const draft: ScheduleDraft = {
    ...base,
    name: schedule.name,
    source: schedule.source_sequence_id ? "playlist" : "collection",
    playlistId: schedule.source_sequence_id ? String(schedule.source_sequence_id) : "",
    collectionId: schedule.category_id && !schedule.source_sequence_id ? String(schedule.category_id) : "",
    order: schedule.playlist ? "in_order" : "random",
    timeLimit: Boolean(pattern.timeRange?.start),
    timeStart: pattern.timeRange?.start || base.timeStart,
    timeEnd: pattern.timeRange?.end || base.timeEnd,
    overlap: schedule.exclusive ? "only" : schedule.blend_enabled ? "mix" : "priority",
    priority: schedule.priority ?? 5,
  };
  if (schedule.type === "holiday" && schedule.holiday_name) {
    draft.when = "holiday";
    draft.holidayName = schedule.holiday_name;
    draft.holidayCountry = schedule.holiday_country || base.holidayCountry;
  } else if (schedule.type === "holiday") {
    return null;
  } else if (schedule.type === "monthly") {
    const months = (pattern.months ?? []).map(Number);
    const days = (pattern.monthDays ?? []).map(Number);
    if (!days.length) return null;
    if (months.length === 1) {
      draft.when = "specific";
      draft.specificMonth = months[0] ?? 12;
      draft.specificDays = days;
    } else {
      draft.when = "monthly";
      draft.monthDays = days;
      draft.months = months;
    }
  } else if (schedule.type === "yearly") {
    const s = datePart(schedule.start_date);
    const e = datePart(schedule.end_date) || s;
    draft.when = "yearly";
    draft.startMonth = Number(s.slice(5, 7)) || 1;
    draft.startDay = Number(s.slice(8, 10)) || 1;
    draft.endMonth = Number(e.slice(5, 7)) || draft.startMonth;
    draft.endDay = Number(e.slice(8, 10)) || draft.startDay;
  } else if (schedule.type === "weekly") {
    draft.when = "weekly";
    draft.weekDays = (pattern.weekDays ?? []).map((d) => d.toLowerCase()).filter((d): d is Weekday => (WEEKDAYS as readonly string[]).includes(d));
  } else if (schedule.end_date) {
    draft.when = "dates";
    draft.startDate = datePart(schedule.start_date);
    draft.endDate = datePart(schedule.end_date);
  } else {
    draft.when = "always";
  }
  return draft;
}

export function daysInMonth(month: number): number {
  return [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 31;
}
