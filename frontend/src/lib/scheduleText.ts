// Schedules described in sentences: "Halloween intros play every year from Oct 1 to Oct 31."
import { formatDay, formatTime, MONTH_NAMES } from "./format";
import { parsePattern, type ScheduleDraft } from "./scheduleDraft";
import type { Schedule } from "./types";

const SHORT_MONTHS = MONTH_NAMES.map((m) => m.slice(0, 3));

export function listWords(words: string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function weekdaysText(days: string[]): string {
  const set = new Set(days.map((d) => d.toLowerCase()));
  if (set.size === 7) return "every day";
  if (set.size === 5 && !set.has("saturday") && !set.has("sunday")) return "every weekday";
  if (set.size === 2 && set.has("saturday") && set.has("sunday")) return "every weekend";
  const order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
  return `every ${listWords(order.filter((d) => set.has(d)).map(cap))}`;
}

function timeText(range?: { start?: string; end?: string }): string {
  if (!range?.start) return "";
  const end = range.end || "23:59";
  if (range.start === "00:00" && end === "23:59") return "";
  return `, from ${formatTime(range.start)} to ${formatTime(end)}`;
}

function whatText(collection: string | undefined, isPlaylist: boolean, playlistName?: string): string {
  if (isPlaylist) return playlistName ? `The ${playlistName} playlist plays` : "A playlist plays";
  return collection ? `${collection} intros play` : "Intros play";
}

/** Sentence for a saved schedule. */
export function describeSchedule(s: Schedule, collectionName?: string, playlistName?: string): string {
  const pattern = parsePattern(s);
  const what = whatText(collectionName ?? s.category?.name, Boolean(s.sequence), playlistName);
  let when: string;
  switch (s.type) {
    case "yearly":
      when = `every year from ${formatDay(s.start_date)} to ${formatDay(s.end_date ?? s.start_date)}`;
      break;
    case "holiday":
      when = s.holiday_name ? `on ${s.holiday_name} every year` : `every year from ${formatDay(s.start_date)} to ${formatDay(s.end_date)}`;
      break;
    case "weekly":
      when = weekdaysText(pattern.weekDays ?? []);
      break;
    case "monthly": {
      const months = pattern.months ?? [];
      const days = pattern.monthDays ?? [];
      if (months.length === 1 && days.length) {
        when = `every year on ${SHORT_MONTHS[(months[0] ?? 1) - 1]} ${listWords([...days].sort((a, b) => a - b).map(String))}`;
        break;
      }
      const dayText = days.length ? `on day ${listWords(days.map(String))}` : "on certain days";
      const monthText = months.length && months.length < 12 ? ` of ${listWords(months.map((m) => SHORT_MONTHS[m - 1] ?? ""))}` : " of every month";
      when = `${dayText}${monthText}`;
      break;
    }
    case "daily":
      when = s.end_date
        ? dateRangeText(formatDay(s.start_date, true), formatDay(s.end_date, true))
        : "every day";
      break;
    default:
      when = "on a custom schedule";
  }
  return `${what} ${when}${timeText(pattern.timeRange)}.`;
}

/** "on Nov 8, 2026" for one day, not "every day from Nov 8, 2026 to Nov 8, 2026". */
function dateRangeText(first: string, last: string): string {
  return first === last ? `on ${first}` : `every day from ${first} to ${last}`;
}

/** Live preview while filling in the wizard. */
export function describeDraft(d: ScheduleDraft, collectionName?: string, playlistName?: string): string[] {
  const what = d.source === "playlist" ? (playlistName ? `The ${playlistName} playlist plays` : "A playlist plays") : whatText(collectionName, false);
  let when: string;
  switch (d.when) {
    case "yearly":
      when = `every year from ${SHORT_MONTHS[d.startMonth - 1]} ${d.startDay} to ${SHORT_MONTHS[d.endMonth - 1]} ${d.endDay}`;
      break;
    case "dates":
      when = d.endDate
        ? dateRangeText(formatDay(d.startDate, true), formatDay(d.endDate, true))
        : `every day from ${formatDay(d.startDate, true)} on`;
      break;
    case "weekly":
      when = d.weekDays.length ? weekdaysText(d.weekDays) : "on the days you pick";
      break;
    case "holiday":
      when = d.holidayName ? `on ${d.holidayName} every year` : "on the holiday you pick, every year";
      break;
    case "monthly": {
      const days = [...d.monthDays].sort((a, b) => a - b);
      const months = [...d.months].sort((a, b) => a - b);
      const dayText = days.length ? `on day ${listWords(days.map(String))}` : "on the days you pick";
      when = `${dayText} of ${months.length && months.length < 12 ? listWords(months.map((m) => SHORT_MONTHS[m - 1] ?? "")) : "every month"}`;
      break;
    }
    case "specific": {
      const days = [...d.specificDays].sort((a, b) => a - b);
      when = days.length ? `every year on ${SHORT_MONTHS[d.specificMonth - 1]} ${listWords(days.map(String))}` : "on the dates you pick, every year";
      break;
    }
    default:
      when = "all the time";
  }
  const time = d.timeLimit ? timeText({ start: d.timeStart, end: d.timeEnd }) : "";
  const lines = [`${what} ${when}${time}.`];
  if (d.source === "playlist") lines.push("Its steps play in order.");
  else lines.push(d.order === "random" ? "One is picked at random each time." : "They all play, one after another.");
  if (d.overlap === "only") lines.push("While it's on, only these intros play (rules and the never-play list still go first).");
  else if (d.overlap === "mix") lines.push("If another schedule is on at the same time, the intros are mixed together.");
  else lines.push(`If another schedule is on at the same time, the more important one wins (this one is ${d.priority} out of 10).`);
  return lines;
}
