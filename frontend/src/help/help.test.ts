import { ARTICLES, getArticle, searchHelp } from ".";
import { ADVANCED_PAGES } from "../pages/settings/advanced/pages";
import { sectionId } from "../components/Markdown";

describe("help articles", () => {
  it("bundles every article with a title", () => {
    expect(ARTICLES.length).toBe(30);
    for (const a of ARTICLES) {
      expect(a.title.length).toBeGreaterThan(3);
      expect(a.body.length).toBeGreaterThan(100);
    }
  });

  it("only links to articles that exist", () => {
    for (const a of ARTICLES) {
      for (const [, slug] of a.body.matchAll(/\(help:([a-z-]+)\)/g)) {
        expect(getArticle(slug ?? ""), `${a.slug} links to help:${slug}`).toBeDefined();
      }
    }
  });

  it("finds articles by words people use", () => {
    expect(searchHelp("apple tv").map((h) => h.article.slug)).toContain("devices");
    expect(searchHelp("docker")[0]?.article.slug).toBe("folder-mapping");
    expect(searchHelp("zzzz")).toEqual([]);
    expect(searchHelp("loudness")[0]?.article.slug).toBe("media-tools");
    expect(searchHelp("kids-safe").map((h) => h.article.slug)).toContain("rules");
    expect(searchHelp("swiftfin").map((h) => h.article.slug)).toContain("missed-intros");
    expect(searchHelp("second jellyfin")[0]?.article.slug).toBe("several-servers");
    expect(searchHelp("play a test").map((h) => h.article.slug)).toContain("play-a-test");
    expect(searchHelp("nexroll")[0]?.article.slug).toBe("moving-from-nexroll");
  });

  it("shows search snippets without link addresses", () => {
    for (const q of ["roku", "playlist", "token", "plugin", "schedule"]) {
      for (const hit of searchHelp(q)) {
        expect(hit.snippet, `${q} in ${hit.article.slug}`).not.toMatch(/help:|app:|\]\(/);
      }
    }
  });

  it("only links to pages that exist", () => {
    const pages = [
      /^\/$/, /^\/videos(\/(collections|community|watch))?$/, /^\/schedules(\/(new|rules|rules\/new|never-play))?$/,
      /^\/played$/, /^\/servers(\/(plex|jellyfin|emby))?$/, /^\/help(\/troubleshoot|\/report)?$/,
      /^\/settings$/, /^\/settings\/advanced\/[a-z-]+$/, /^\/welcome$/,
    ];
    for (const a of ARTICLES) {
      for (const [, path] of a.body.matchAll(/\(app:([^)\s]+)\)/g)) {
        const bare = (path ?? "").split("#")[0]!.split("?")[0]!;
        expect(pages.some((re) => re.test(bare)), `${a.slug} links to app:${path}`).toBe(true);
      }
    }
  });

  it("opens a page's help at a section that exists", () => {
    const withSection = ADVANCED_PAGES.filter((p) => p.help?.includes("#"));
    expect(withSection.map((p) => p.slug).sort()).toEqual(["api-keys", "logs", "trash"]);
    for (const page of withSection) {
      const [slug, section] = (page.help ?? "").split("#");
      const article = getArticle(slug ?? "");
      const ids = [...(article?.body ?? "").matchAll(/^#{2,3} (.+)$/gm)].map((m) => sectionId(m[1] ?? ""));
      expect(ids, `${page.slug} opens ${page.help}`).toContain(sectionId(section ?? ""));
    }
  });
});
