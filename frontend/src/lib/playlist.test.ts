// Ported from the old interface's utils/sequenceValidator.test.js, plus
// checks for the plain-language messages.
import {
  cloneSequenceWithIds,
  parseSequence,
  sanitizeSequence,
  sequenceHasUnsavedChanges,
  stringifySequence,
  validateBlock,
  validateSequence,
  withoutImportNotes,
  type Block,
} from "./playlist";

describe("sanitizeSequence", () => {
  it("keeps a sequential block's category and count", () => {
    // Saving used to drop both, so the block played nothing.
    expect(sanitizeSequence([{ id: "ui-1", type: "sequential", category_id: 7, count: 3 }])).toEqual([
      { type: "sequential", category_id: 7, count: 3 },
    ]);
  });

  it("keeps a block condition and a cleaned alternative", () => {
    const condition = { match: "all" as const, rules: [{ kind: "trailers_available", min: 1 }] };
    const [saved] = sanitizeSequence([
      {
        id: "ui-2",
        type: "coming_soon_list",
        layout: "grid",
        condition,
        otherwise: { type: "random", category_id: 4, count: 2, label: "ignored", ui_only: true },
      },
    ]);
    expect(saved).toEqual({ type: "coming_soon_list", layout: "grid", condition, otherwise: { type: "random", category_id: 4, count: 2 } });
  });

  it("keeps a library trailers block's settings", () => {
    expect(sanitizeSequence([{ id: "ui-3", type: "library_trailers", count: 3, mode: "newest", genres: ["Horror"], match_playing: true }])).toEqual([
      { type: "library_trailers", count: 3, mode: "newest", genres: ["Horror"], match_playing: true },
    ]);
  });

  it("keeps the Else if flag, with or without a condition", () => {
    const condition = { match: "all" as const, rules: [{ kind: "genre", values: ["Horror"] }] };
    expect(
      sanitizeSequence([
        { id: "ui-4", type: "random", category_id: 1, count: 1, condition },
        { id: "ui-5", type: "random", category_id: 2, count: 1, else_if: true },
        { id: "ui-6", type: "random", category_id: 3, count: 1, else_if: false },
      ]).map((block) => block.else_if),
    ).toEqual([undefined, true, undefined]);
  });

  it("drops an empty condition and any alternative left behind", () => {
    const [saved] = sanitizeSequence([{ type: "fixed", preroll_ids: [1], condition: { rules: [] }, otherwise: { type: "random", category_id: 4 } }]);
    expect(saved).toEqual({ type: "fixed", preroll_ids: [1] });
  });

  it("keeps saved flow geometry through JSON and cloned ids; malformed points are dropped", () => {
    const [block] = cloneSequenceWithIds(
      parseSequence(
        stringifySequence([
          {
            type: "fixed",
            preroll_ids: [1],
            flow_positions: { simple_b: { x: -210, y: 150 }, advanced_if: { x: 40, y: -90 }, advanced_o: { x: Infinity, y: 0 }, unknown: { x: 0, y: 0 } },
          },
        ]),
      ) ?? [],
    );
    expect(block?.flow_positions).toEqual({ simple_b: { x: -210, y: 150 }, advanced_if: { x: 40, y: -90 } });
  });
});

describe("sequenceHasUnsavedChanges", () => {
  const saved = {
    name: "Friday Night",
    description: "Weekend opener",
    blocks: [{ type: "fixed", preroll_ids: [1] }, { type: "random", category_id: 2, count: 1 }] as Block[],
  };

  it("a freshly opened playlist is not dirty despite its cloned ids", () => {
    const blocks = cloneSequenceWithIds(saved.blocks);
    expect(blocks[0]?.id).toBeDefined();
    expect(sequenceHasUnsavedChanges(blocks, saved.name, saved.description, saved)).toBe(false);
  });

  it("changing a step is dirty", () => {
    const blocks = cloneSequenceWithIds(saved.blocks);
    blocks[1] = { ...blocks[1]!, count: 3 };
    expect(sequenceHasUnsavedChanges(blocks, saved.name, saved.description, saved)).toBe(true);
  });

  it("adding, removing and reordering steps are all dirty", () => {
    const blocks = cloneSequenceWithIds(saved.blocks);
    expect(sequenceHasUnsavedChanges([...blocks, { type: "separator", duration: 3 }], saved.name, saved.description, saved)).toBe(true);
    expect(sequenceHasUnsavedChanges([blocks[0]!], saved.name, saved.description, saved)).toBe(true);
    expect(sequenceHasUnsavedChanges([blocks[1]!, blocks[0]!], saved.name, saved.description, saved)).toBe(true);
  });

  it("renaming is dirty, surrounding spaces are not", () => {
    const blocks = cloneSequenceWithIds(saved.blocks);
    expect(sequenceHasUnsavedChanges(blocks, "Saturday Night", saved.description, saved)).toBe(true);
    expect(sequenceHasUnsavedChanges(blocks, saved.name, "Something else", saved)).toBe(true);
    expect(sequenceHasUnsavedChanges(blocks, "  Friday Night  ", "  Weekend opener  ", saved)).toBe(false);
  });

  it("a condition added to a step is dirty", () => {
    const blocks = cloneSequenceWithIds(saved.blocks);
    blocks[0] = { ...blocks[0]!, condition: { match: "all", rules: [{ kind: "genre", values: ["Horror"] }] } };
    expect(sequenceHasUnsavedChanges(blocks, saved.name, saved.description, saved)).toBe(true);
  });

  it("an untouched new playlist is not dirty, any content makes it dirty", () => {
    expect(sequenceHasUnsavedChanges([], "", "", null)).toBe(false);
    expect(sequenceHasUnsavedChanges([], "   ", "  ", null)).toBe(false);
    expect(sequenceHasUnsavedChanges([{ type: "fixed", preroll_ids: [1] }], "", "", null)).toBe(true);
    expect(sequenceHasUnsavedChanges([], "Named but empty", "", null)).toBe(true);
  });
});

describe("validateBlock and validateSequence", () => {
  const categories = [{ id: 1, name: "Halloween" }];
  const prerolls = [{ id: 10 }, { id: 11 }];

  it("accepts finished steps", () => {
    expect(validateBlock({ type: "random", category_id: 1, count: 2 }, categories, prerolls)).toEqual([]);
    expect(validateBlock({ type: "fixed", preroll_ids: [10, 11] }, categories, prerolls)).toEqual([]);
    expect(validateBlock({ type: "nexup_trailers", count: 3, ratings: ["PG", "PG-13"] }, categories, prerolls)).toEqual([]);
  });

  it("says what to fix in plain words, never an id", () => {
    expect(validateBlock({ type: "random", count: 1 })).toEqual(["Pick a collection."]);
    const gone = validateBlock({ type: "random", category_id: 12, count: 1 }, categories);
    expect(gone[0]).toMatch(/doesn't exist anymore/);
    expect(gone.join(" ")).not.toMatch(/12/);
    expect(validateBlock({ type: "random", category_id: 1, count: 11 }, categories)).toEqual(["Play 10 or fewer."]);
    expect(validateBlock({ type: "fixed", preroll_ids: [] })).toEqual(["Pick at least one video."]);
    expect(validateBlock({ type: "fixed", preroll_ids: [10, 99] }, categories, prerolls)).toEqual(["One of the videos isn't in your library anymore."]);
    expect(validateBlock({ type: "nexup_trailers", count: 30 })).toEqual(["Play 20 trailers or fewer."]);
  });

  it("checks the Otherwise step and every rule", () => {
    const block: Block = {
      type: "random",
      category_id: 1,
      count: 1,
      condition: { match: "all", rules: [{ kind: "genre", values: [] }, { kind: "time_window", start: "18:00" }] },
      otherwise: { type: "random", count: 1 },
    };
    expect(validateBlock(block, categories)).toEqual(["Otherwise: Pick a collection.", "Add at least one genre.", "Enter both times, like 18:00 and 22:00."]);
  });

  it("numbers the steps that need fixing", () => {
    expect(validateSequence([])).toEqual({ valid: false, errors: ["Add at least one step."] });
    const result = validateSequence([{ type: "random", category_id: 1, count: 1 }, { type: "fixed" }], categories, prerolls);
    expect(result).toEqual({ valid: false, errors: ["Step 2: Pick at least one video."] });
  });
});

describe("withoutImportNotes", () => {
  it("drops the importer's match notes", () => {
    expect(withoutImportNotes([{ type: "fixed", preroll_ids: [1], _unmatched: true, _missing_prerolls: ["x"] }])).toEqual([{ type: "fixed", preroll_ids: [1] }]);
  });
});
