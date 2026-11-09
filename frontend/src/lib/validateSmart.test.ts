import {
  EMPTY_RULE,
  MESSAGES,
  checkNumber,
  checkTags,
  checkWhole,
  cleanDecade,
  draftToRuleIn,
  playbackSchema,
  ruleProblems,
  ruleSchema,
  ruleToDraft,
  splitList,
  weightLabel,
  type RuleDraft,
} from "./validateSmart";
import { badgeFor, pluginWorking } from "./capabilities";
import { loudnessWords } from "./media";
import { timeAgo } from "./stats";
import { ApiError, describeError, isAdminOnly } from "./errors";
import type { Rule } from "./rules";

const draft = (over: Partial<RuleDraft>): RuleDraft => ({ ...EMPTY_RULE, name: "Kids", collection_id: "3", ...over });

describe("lists and numbers", () => {
  it("splits comma and line lists without repeats", () => {
    expect(splitList(" Horror, sci-fi\nHORROR ,, Drama ")).toEqual(["Horror", "sci-fi", "Drama"]);
    expect(splitList("")).toEqual([]);
  });

  it("checks whole numbers and decimals against limits", () => {
    expect(checkWhole("4", 1, 48, "x")).toEqual({ ok: true, value: 4 });
    expect(checkWhole("0", 1, 48, "x").ok).toBe(false);
    expect(checkWhole("4.5", 1, 48, "x").ok).toBe(false);
    expect(checkWhole("four", 1, 48, "x").ok).toBe(false);
    expect(checkNumber("-23,5", -31, -10, "x")).toEqual({ ok: true, value: -23.5 });
    expect(checkNumber("-9", -31, -10, "x").ok).toBe(false);
  });

  it("reads decades the way the server does", () => {
    expect(cleanDecade("1985")).toBe("1980s");
    expect(cleanDecade("80s")).toBe("1980s");
    expect(cleanDecade("1990s")).toBe("1990s");
    expect(cleanDecade("eighties")).toBeNull();
  });

  it("limits no-intro tags", () => {
    expect(checkTags("no-intro, nointro")).toEqual({ ok: true, value: ["no-intro", "nointro"] });
    expect(checkTags("x".repeat(61))).toEqual({ ok: false, message: MESSAGES.tag });
  });

  it("names weights in words", () => {
    expect([1, 3, 5, 7, 10].map(weightLabel)).toEqual(["Rarely", "Less often", "Normal", "More often", "Often"]);
  });
});

describe("rule form", () => {
  it("accepts a simple kids rule", () => {
    expect(ruleProblems(draft({ kids_safe: true }))).toEqual({});
  });

  it("says what's wrong, on the right field", () => {
    const problems = ruleProblems(draft({ name: " ", year_from: "1990", year_to: "1980", media_type: "movie", first_episode_only: true, count: "21", cooldown_hours: "900" }));
    expect(problems.name).toBe("Enter a rule name.");
    expect(problems.year_to).toBe(MESSAGES.yearOrder);
    expect(problems.first_episode_only).toBe(MESSAGES.firstEpisode);
    expect(problems.count).toBe(MESSAGES.count);
    expect(problems.cooldown_hours).toBe(MESSAGES.cooldown);
    expect(ruleProblems(draft({ year_from: "1800" })).year_from).toBe(MESSAGES.year);
  });

  it("needs something to play", () => {
    expect(ruleProblems(draft({ collection_id: "" })).collection_id).toBe(MESSAGES.collection);
    expect(ruleProblems(draft({ source: "videos" })).preroll_ids).toBe(MESSAGES.videos);
  });

  it("gives React Hook Form the same messages", () => {
    const result = ruleSchema.safeParse(draft({ name: "" }));
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(["name"]);
  });

  it("builds the request body the server expects", () => {
    const body = draftToRuleIn(
      draft({ name: "  80s   horror ", genres: "Horror, horror", decades: ["1980s"], year_from: "1980", media_type: "movie", order: "in_order", cooldown_hours: "12", count: "" }),
    );
    expect(body).toEqual({
      name: "80s horror",
      enabled: true,
      when: { genres: ["Horror"], ratings: [], kids_safe: false, decades: ["1980s"], year_from: 1980, year_to: null, libraries: [], users: [], media_type: "movie", first_episode_only: false },
      play: { collection_id: 3, preroll_ids: [], count: null, order: "in_order", cooldown_hours: 0 },
    });
  });

  it("round-trips a saved rule", () => {
    const rule = {
      id: 1, position: 0, summary: "", collection_name: null, plays: [], problem: null, name: "Mia", enabled: false,
      when: { genres: ["Animation"], ratings: ["PG"], kids_safe: true, decades: [], year_from: null, year_to: 2010, libraries: ["Kids"], users: ["mia"], media_type: "episode", first_episode_only: true },
      play: { collection_id: null, preroll_ids: [4, 2], count: 2, order: "random", cooldown_hours: 6 },
    } satisfies Rule;
    const d = ruleToDraft(rule);
    expect(d.source).toBe("videos");
    expect(draftToRuleIn(d)).toEqual({ name: "Mia", enabled: false, when: rule.when, play: rule.play });
  });
});

describe("playback settings form", () => {
  const good = {
    binge_window_hours: "4", kids_safe_ratings: ["G"], unrated_is_kids_safe: false, honor_no_intro_tags: true,
    no_intro_tags: "no-intro, nointro", history_enabled: true, history_retention_days: "90",
    loudness_target_lufs: "-23", loudness_tolerance_lu: "2", watch_sessions: true, links_allow_home_network: false,
  };

  it("turns the boxes into numbers and lists", () => {
    const out = playbackSchema.parse(good);
    expect(out.binge_window_hours).toBe(4);
    expect(out.no_intro_tags).toEqual(["no-intro", "nointro"]);
    expect(out.loudness_target_lufs).toBe(-23);
  });

  it("refuses values the server refuses, with plain messages", () => {
    const result = playbackSchema.safeParse({ ...good, binge_window_hours: "0", history_retention_days: "9999", loudness_target_lufs: "-5", loudness_tolerance_lu: "abc" });
    expect(result.success).toBe(false);
    const byField = Object.fromEntries((result.error?.issues ?? []).map((i) => [i.path[0], i.message]));
    expect(byField).toEqual({ binge_window_hours: MESSAGES.binge, history_retention_days: MESSAGES.retention, loudness_target_lufs: MESSAGES.target, loudness_tolerance_lu: MESSAGES.tolerance });
  });
});

describe("badges and words", () => {
  it("says the plugin works once it has checked in", () => {
    expect(badgeFor("plugin", "jellyfin").label).toBe("Needs plugin");
    expect(badgeFor("plugin", "jellyfin", true)).toEqual({ label: "Works (plugin)", tone: "success" });
    expect(badgeFor("emulated", "plex").label).toBe("Next play only");
    expect(badgeFor("none", "plex").label).toBe("Not possible on Plex");
    expect(pluginWorking({ connected: true, plugin: { connected: true, version: "2.0.0", protocol: 2, last_seen_seconds_ago: 5, note: "" } })).toBe(true);
    expect(pluginWorking({ connected: true, plugin: { connected: false, version: null, protocol: null, last_seen_seconds_ago: null, note: "" } })).toBe(false);
  });

  it("describes loudness with the level", () => {
    expect(loudnessWords({ status: "loud", lufs: -12.4, peak: -0.5 }, -23)).toMatchObject({ label: "Too loud", tone: "warning" });
    expect(loudnessWords({ status: "loud", lufs: -12.4, peak: -0.5 }, -23).detail).toContain("-12.4 LUFS");
    expect(loudnessWords({ status: "ok", lufs: -23.2, peak: -3 }, -23).label).toBe("Loudness OK");
  });

  it("says plainly when only an admin can do something", () => {
    const admin = new ApiError({ kind: "forbidden", status: 403, code: "admin_required", message: "Only an admin can clear play history." });
    const locked = new ApiError({ kind: "forbidden", status: 403, code: "system_collection", message: '"Trailers" is managed by Prerolls Max.' });
    expect(isAdminOnly(admin)).toBe(true);
    expect(describeError(admin).message).toBe("Only an admin can change this.");
    expect(isAdminOnly(locked)).toBe(false);
    expect(describeError(locked).message).toBe('"Trailers" is managed by Prerolls Max.');
  });

  it("says how long ago", () => {
    const now = Date.parse("2026-11-08T12:00:00Z");
    expect(timeAgo("2026-11-08T11:58:00Z", now)).toBe("2 min ago");
    expect(timeAgo("2026-11-08T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-11-06T12:00:00Z", now)).toBe("2 days ago");
    expect(timeAgo(null, now)).toBe("");
  });
});
