import { checkNameFree, nameKey, nameTakenBy, nameTakenMessage, sharedNameIds } from "./names";

const schedules = [
  { id: 1, name: "Halloween" },
  { id: 2, name: "Christmas" },
];

describe("unique names", () => {
  it("compares names without case or extra spaces", () => {
    expect(nameKey("  Hallo   WEEN ")).toBe("hallo ween");
    expect(nameTakenBy(schedules, " halloween ")?.id).toBe(1);
    expect(nameTakenBy(schedules, "halloween", 1)).toBeUndefined();
  });

  it("uses the same message as the server", () => {
    expect(nameTakenMessage("schedule", "Halloween")).toBe("There's already a schedule called 'Halloween'. Pick another name.");
    expect(checkNameFree("schedule", schedules, "HALLOWEEN", 2, "Christmas")).toBe(
      "There's already a schedule called 'Halloween'. Pick another name.",
    );
    expect(checkNameFree("schedule", schedules, "Easter")).toBeUndefined();
  });

  it("lets an item an old database holds twice keep its own name", () => {
    const twins = [...schedules, { id: 3, name: "halloween" }];
    expect(checkNameFree("schedule", twins, "Halloween", 3, "halloween")).toBeUndefined();
    expect([...sharedNameIds(twins)].sort()).toEqual([1, 3]);
    expect(sharedNameIds(schedules).size).toBe(0);
  });
});
