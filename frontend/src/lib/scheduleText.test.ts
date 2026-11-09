import { describeDraft, describeSchedule } from "./scheduleText";
import { draftToPayload, emptyDraft, scheduleToDraft } from "./scheduleDraft";
import type { Schedule } from "./types";

const base: Schedule = {
  id: 1, name: "Halloween", type: "yearly", start_date: "2000-10-01T00:00:00", end_date: "2000-10-31T23:59:00",
  category_id: 3, category: { id: 3, name: "Halloween" }, playlist: false, is_active: true, next_run: null,
  recurrence_pattern: null, sequence: null, blend_enabled: false, priority: 5, exclusive: false, holiday_name: null, color: null,
};

describe("describeSchedule", () => {
  it("says yearly schedules in a sentence", () => {
    expect(describeSchedule(base)).toBe("Halloween intros play every year from Oct 1 to Oct 31.");
  });
  it("covers weekdays and time windows", () => {
    const s = { ...base, type: "weekly", recurrence_pattern: JSON.stringify({ weekDays: ["saturday", "sunday"], timeRange: { start: "18:00", end: "23:00" } }) };
    expect(describeSchedule(s)).toBe("Halloween intros play every weekend, from 6 pm to 11 pm.");
  });
  it("names date ranges with the year", () => {
    const s = { ...base, type: "daily", start_date: "2026-12-01T00:00:00", end_date: "2026-12-26T23:59:00" };
    expect(describeSchedule(s)).toBe("Halloween intros play every day from Dec 1, 2026 to Dec 26, 2026.");
  });
  it("says a single day as one day", () => {
    const s = { ...base, type: "daily", start_date: "2026-11-08T00:00:00", end_date: "2026-11-08T23:59:00" };
    expect(describeSchedule(s)).toBe("Halloween intros play on Nov 8, 2026.");
    const d = { ...emptyDraft(), when: "dates" as const, startDate: "2026-11-08", endDate: "2026-11-08" };
    expect(describeDraft(d, "Halloween")[0]).toBe("Halloween intros play on Nov 8, 2026.");
  });
});

describe("wizard draft", () => {
  it("previews the draft in plain words", () => {
    const d = { ...emptyDraft(), overlap: "only" as const };
    expect(describeDraft(d, "Halloween")).toEqual([
      "Halloween intros play every year from Oct 1 to Oct 31.",
      "One is picked at random each time.",
      "While it's on, only these intros play (rules and the never-play list still go first).",
    ]);
  });
  it("builds the server payload", () => {
    const d = { ...emptyDraft(), name: " Spooky ", collectionId: "3", timeLimit: true, timeStart: "18:00", timeEnd: "23:00" };
    expect(draftToPayload(d)).toMatchObject({
      name: "Spooky", type: "yearly", start_date: "2000-10-01T00:00", end_date: "2000-10-31T23:59",
      category_id: 3, playlist: false, exclusive: false, blend_enabled: false, priority: 5,
      recurrence_pattern: JSON.stringify({ timeRange: { start: "18:00", end: "23:00" } }),
    });
  });
  it("round-trips a saved schedule", () => {
    const d = scheduleToDraft(base);
    expect(d).toMatchObject({ when: "yearly", startMonth: 10, startDay: 1, endMonth: 10, endDay: 31, collectionId: "3" });
  });
  it("leaves playlist schedules to the Advanced editor", () => {
    expect(scheduleToDraft({ ...base, sequence: "[]" })).toBeNull();
  });
});
