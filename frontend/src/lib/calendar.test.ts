import { monthGrid, pickWinners, planFor, playsOn } from "./calendar";
import type { Schedule } from "./types";

function sched(over: Partial<Schedule>): Schedule {
  return {
    id: 1,
    name: "S",
    type: "daily",
    start_date: "2026-01-01T00:00:00",
    end_date: null,
    category_id: 1,
    category: null,
    playlist: false,
    is_active: true,
    next_run: null,
    recurrence_pattern: null,
    sequence: null,
    blend_enabled: false,
    priority: 5,
    exclusive: false,
    holiday_name: null,
    color: null,
    ...over,
  };
}

const d = (iso: string) => {
  const [y, m, day] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, day!);
};

describe("playsOn", () => {
  it("follows a yearly window, including one that wraps past New Year", () => {
    const oct = sched({ type: "yearly", start_date: "2000-10-01T00:00", end_date: "2000-10-31T23:59" });
    expect(playsOn(oct, d("2027-10-15"))).toBe(true);
    expect(playsOn(oct, d("2027-11-01"))).toBe(false);
    const winter = sched({ type: "yearly", start_date: "2000-12-20T00:00", end_date: "2000-01-05T23:59" });
    expect(playsOn(winter, d("2027-01-03"))).toBe(true);
    expect(playsOn(winter, d("2027-01-06"))).toBe(false);
  });

  it("follows weekdays and the date range", () => {
    const weekends = sched({ type: "weekly", recurrence_pattern: '{"weekDays":["saturday","sunday"]}', end_date: "2026-12-31T23:59" });
    expect(playsOn(weekends, d("2026-11-07"))).toBe(true); // Saturday
    expect(playsOn(weekends, d("2026-11-09"))).toBe(false); // Monday
    expect(playsOn(weekends, d("2027-01-02"))).toBe(false); // after the end
  });

  it("follows days of the month and months", () => {
    const s = sched({ type: "monthly", start_date: "2000-01-01T00:00", recurrence_pattern: '{"months":[12],"monthDays":[24,25]}' });
    expect(playsOn(s, d("2026-12-24"))).toBe(true);
    expect(playsOn(s, d("2026-11-24"))).toBe(false);
    expect(playsOn(s, d("2026-12-26"))).toBe(false);
  });

  it("puts a holiday on its date", () => {
    const s = sched({ type: "holiday", holiday_name: "Thanksgiving Day", start_date: "2026-11-26T00:00", end_date: "2026-11-26T23:59" });
    expect(playsOn(s, d("2026-11-26"))).toBe(true);
    expect(playsOn(s, d("2026-11-25"))).toBe(false);
  });

  it("never shows a schedule that's off", () => {
    expect(playsOn(sched({ is_active: false }), d("2026-05-05"))).toBe(false);
  });
});

describe("planFor", () => {
  const a = sched({ id: 1, name: "Everyday", priority: 3 });
  const b = sched({ id: 2, name: "Halloween", priority: 8 });
  it("picks the most important when two overlap", () => {
    const plan = planFor([a, b], d("2026-10-31"));
    expect(plan.on.map((s) => s.name)).toEqual(["Halloween", "Everyday"]);
    expect(plan.playing.map((s) => s.name)).toEqual(["Halloween"]);
  });
  it("lets an only-these schedule win even with a lower number", () => {
    const plan = planFor([b, { ...a, exclusive: true }], d("2026-10-31"));
    expect(plan.playing.map((s) => s.name)).toEqual(["Everyday"]);
  });
  it("mixes two schedules set to mix", () => {
    const plan = planFor([{ ...a, blend_enabled: true }, { ...b, blend_enabled: true }], d("2026-10-31"));
    expect(plan.playing).toHaveLength(2);
  });
  it("picks the winner among the schedules on right now (Home)", () => {
    const plan = pickWinners([a, b]);
    expect(plan.playing.map((s) => s.name)).toEqual(["Halloween"]);
    expect(plan.why).toContain("Halloween is the most important");
  });
});

describe("monthGrid", () => {
  it("starts on Monday and covers the month", () => {
    const weeks = monthGrid(2026, 11);
    expect(weeks[0]![0]!.getDay()).toBe(1);
    expect(weeks.flat().some((day) => day.getDate() === 30 && day.getMonth() === 10)).toBe(true);
  });
});
