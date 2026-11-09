import { draftToPayload, emptyDraft, scheduleToDraft } from "./scheduleDraft";
import { describeDraft } from "./scheduleText";
import type { Schedule } from "./types";

const now = new Date(2026, 10, 8);

function asSchedule(payload: ReturnType<typeof draftToPayload>, id = 1): Schedule {
  return {
    id,
    category: null,
    is_active: true,
    next_run: null,
    color: null,
    ...payload,
  } as Schedule;
}

describe("holiday, monthly and dates-every-year schedules", () => {
  it("a holiday sends the holiday and country, and comes back the same", () => {
    const draft = { ...emptyDraft(now), name: "Turkey day", collectionId: "3", when: "holiday" as const, holidayCountry: "US", holidayName: "Thanksgiving Day" };
    const payload = draftToPayload(draft, now);
    expect(payload).toMatchObject({ type: "holiday", holiday_name: "Thanksgiving Day", holiday_country: "US", category_id: 3 });
    const back = scheduleToDraft(asSchedule(payload));
    expect(back).toMatchObject({ when: "holiday", holidayName: "Thanksgiving Day", holidayCountry: "US" });
    expect(describeDraft(draft, "Fall")[0]).toBe("Fall intros play on Thanksgiving Day every year.");
  });

  it("days of the month become a monthly schedule", () => {
    const draft = { ...emptyDraft(now), name: "Paydays", collectionId: "1", when: "monthly" as const, monthDays: [15, 1], months: [] };
    const payload = draftToPayload(draft, now);
    expect(payload.type).toBe("monthly");
    expect(JSON.parse(payload.recurrence_pattern ?? "{}")).toEqual({ monthDays: [1, 15] });
    expect(scheduleToDraft(asSchedule(payload))).toMatchObject({ when: "monthly", monthDays: [1, 15], months: [] });
  });

  it("dates every year are one month and its days", () => {
    const draft = { ...emptyDraft(now), name: "Holidays", collectionId: "1", when: "specific" as const, specificMonth: 12, specificDays: [31, 24, 25] };
    const payload = draftToPayload(draft, now);
    expect(JSON.parse(payload.recurrence_pattern ?? "{}")).toEqual({ months: [12], monthDays: [24, 25, 31] });
    expect(scheduleToDraft(asSchedule(payload))).toMatchObject({ when: "specific", specificMonth: 12, specificDays: [24, 25, 31] });
    expect(describeDraft(draft, "Xmas")[0]).toBe("Xmas intros play every year on Dec 24, 25 and 31.");
  });

  it("a playlist sends its steps and remembers which playlist it was", () => {
    const playlists = [{ id: 7, name: "Pre-show", description: null, blocks: [{ type: "random", category_id: 2, count: 1, id: "ui" }] }];
    const draft = { ...emptyDraft(now), name: "Fridays", source: "playlist" as const, playlistId: "7", when: "always" as const };
    const payload = draftToPayload(draft, now, playlists);
    expect(payload).toMatchObject({ category_id: null, source_sequence_id: 7, playlist: false });
    expect(JSON.parse(payload.sequence ?? "[]")).toEqual([{ type: "random", category_id: 2, count: 1 }]);
    expect(scheduleToDraft(asSchedule(payload))).toMatchObject({ source: "playlist", playlistId: "7" });
  });

  it("switching back from a holiday clears the holiday fields", () => {
    const payload = draftToPayload({ ...emptyDraft(now), name: "x", collectionId: "1", when: "yearly" }, now);
    expect(payload).toMatchObject({ holiday_name: null, holiday_country: null, sequence: null, source_sequence_id: null });
  });
});
