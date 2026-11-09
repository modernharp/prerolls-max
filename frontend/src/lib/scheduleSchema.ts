// Checks for the "When they play" wizard. Messages match the server's
// where the server has the same rule (validation.py).
import { z } from "zod";
import { checkDateRange, cleanName, cleanTimeHHMM, parseDate } from "./validate";
import { daysInMonth, WEEKDAYS, type ScheduleDraft } from "./scheduleDraft";
import { MONTH_NAMES } from "./format";

export const STEP_FIELDS: (keyof ScheduleDraft)[][] = [
  ["name", "source", "collectionId", "playlistId", "order"],
  [
    "when", "startMonth", "startDay", "endMonth", "endDay", "startDate", "endDate", "weekDays", "holidayCountry", "holidayName",
    "monthDays", "months", "specificMonth", "specificDays", "timeLimit", "timeStart", "timeEnd",
  ],
  ["overlap", "priority"],
];

export const scheduleSchema = z
  .object({
    name: z.string(),
    source: z.enum(["collection", "playlist"]),
    collectionId: z.string(),
    playlistId: z.string(),
    order: z.enum(["random", "in_order"]),
    when: z.enum(["yearly", "dates", "weekly", "always", "holiday", "monthly", "specific"]),
    startMonth: z.coerce.number().int().min(1).max(12),
    startDay: z.coerce.number().int().min(1).max(31),
    endMonth: z.coerce.number().int().min(1).max(12),
    endDay: z.coerce.number().int().min(1).max(31),
    startDate: z.string(),
    endDate: z.string(),
    weekDays: z.array(z.enum(WEEKDAYS)),
    holidayCountry: z.string(),
    holidayName: z.string(),
    monthDays: z.array(z.number().int().min(1).max(31)),
    months: z.array(z.number().int().min(1).max(12)),
    specificMonth: z.coerce.number().int().min(1).max(12),
    specificDays: z.array(z.number().int().min(1).max(31)),
    timeLimit: z.boolean(),
    timeStart: z.string(),
    timeEnd: z.string(),
    overlap: z.enum(["only", "mix", "priority"]),
    priority: z.coerce.number({ invalid_type_error: "Enter a number from 1 to 10." }).int("Enter a whole number from 1 to 10.").min(1, "Use a number from 1 to 10.").max(10, "Use a number from 1 to 10."),
  })
  .superRefine((d, ctx) => {
    const add = (path: keyof ScheduleDraft, message: string) => ctx.addIssue({ code: "custom", path: [path], message });

    const name = cleanName(d.name, { what: "schedule name" });
    if (!name.ok) add("name", name.message);
    if (d.source === "collection" && !d.collectionId) add("collectionId", "Pick the collection to play.");
    if (d.source === "playlist" && !d.playlistId) add("playlistId", "Pick the playlist to play.");

    if (d.when === "yearly") {
      if (d.startDay > daysInMonth(d.startMonth)) add("startDay", `${MONTH_NAMES[d.startMonth - 1]} only has ${daysInMonth(d.startMonth)} days.`);
      if (d.endDay > daysInMonth(d.endMonth)) add("endDay", `${MONTH_NAMES[d.endMonth - 1]} only has ${daysInMonth(d.endMonth)} days.`);
    }
    if (d.when === "dates") {
      const start = parseDate(d.startDate);
      if (!start.ok) add("startDate", start.message);
      if (d.endDate) {
        const end = parseDate(d.endDate);
        if (!end.ok) add("endDate", end.message);
        else if (start.ok) {
          const range = checkDateRange(start.value, end.value, "first day", "last day");
          if (range) add("endDate", range);
        }
      }
    }
    if (d.when === "weekly" && !d.weekDays.length) add("weekDays", "Pick at least one day.");
    if (d.when === "holiday") {
      if (!d.holidayCountry) add("holidayCountry", "Pick the country whose holidays to use.");
      if (!d.holidayName) add("holidayName", "Pick a holiday.");
    }
    if (d.when === "monthly" && !d.monthDays.length) add("monthDays", "Pick at least one day of the month.");
    if (d.when === "specific") {
      const max = daysInMonth(d.specificMonth);
      if (!d.specificDays.length) add("specificDays", "Pick at least one date.");
      else if (d.specificDays.some((day) => day > max)) {
        add("specificDays", `${MONTH_NAMES[d.specificMonth - 1]} only has ${max} days.`);
      }
    }
    if (d.timeLimit) {
      const s = cleanTimeHHMM(d.timeStart);
      const e = cleanTimeHHMM(d.timeEnd);
      if (!s.ok) add("timeStart", s.message);
      if (!e.ok) add("timeEnd", e.message);
      if (s.ok && e.ok && s.value === e.value) add("timeEnd", "The end time must be different from the start time.");
    }
  });
