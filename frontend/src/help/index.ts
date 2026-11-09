// Help articles are Markdown files in this folder, bundled with the app so
// Help works offline. The first "# Heading" line is the title.

export interface HelpArticle {
  slug: string;
  title: string;
  summary: string;
  group: "Start here" | "Intro videos" | "When they play" | "Media servers" | "Advanced" | "Reference";
  body: string;
}

const files = import.meta.glob("./*.md", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const META: Omit<HelpArticle, "title" | "body">[] = [
  { slug: "getting-started", group: "Start here", summary: "Four steps from a fresh install to an intro playing before a movie." },
  { slug: "moving-from-nexroll", group: "Start here", summary: "Prerolls Max replaces NeXroll: stop it, remove its plugin and bring your setup over. Or keep both, carefully." },
  { slug: "intro-not-playing", group: "Start here", summary: "The usual reasons an intro doesn't play, and how to fix each one." },
  { slug: "faq", group: "Start here", summary: "Short answers to the questions people ask most." },
  { slug: "missed-intros", group: "Start here", summary: "The warnings on Home when a movie started without its intro, and the fix for each app." },
  { slug: "intro-videos", group: "Intro videos", summary: "Uploading videos, which files work, and using collections." },
  { slug: "community", group: "Intro videos", summary: "Getting free intros from Prerolls.me and Prerolls.uk." },
  { slug: "media-tools", group: "Intro videos", summary: "Even out loudness, make TV-friendly versions, and combine intros into one video for Roku." },
  { slug: "watch-folders", group: "Intro videos", summary: "Add new intro videos from a folder on their own." },
  { slug: "schedules", group: "When they play", summary: "Choosing when intros play, what happens when schedules overlap, and default intros." },
  { slug: "rules", group: "When they play", summary: "Different intros by genre, rating, decade, library or person, checked before schedules." },
  { slug: "never-play", group: "When they play", summary: "Titles that never get an intro, kids-safe intros, and intros only before the first episode." },
  { slug: "weights-and-cooldowns", group: "When they play", summary: "Play some intros more often, and keep an intro from repeating too soon." },
  { slug: "connect-plex", group: "Media servers", summary: "Signing in with Plex and the settings Plex needs." },
  { slug: "connect-jellyfin", group: "Media servers", summary: "API key, the Prerolls Max plugin, and what Jellyfin apps support." },
  { slug: "connect-emby", group: "Media servers", summary: "API key, Cinema Intros, and what Emby apps support." },
  { slug: "folder-mapping", group: "Media servers", summary: "When your media server sees your intro folder under a different path, as in Docker." },
  { slug: "devices", group: "Media servers", summary: "Which apps and devices play intros, and workarounds for the ones that don't." },
  { slug: "several-servers", group: "Media servers", summary: "Two Plex or Jellyfin servers, or all three kinds: add, name, switch off and disconnect each one." },
  { slug: "play-a-test", group: "Media servers", summary: "Ask a media server what it would play before a movie, and why when it's nothing." },
  { slug: "playlists", group: "Advanced", summary: "Several intros in a set order, with steps that depend on the movie." },
  { slug: "movie-trailers", group: "Advanced", summary: "Trailers for upcoming movies from Radarr and Sonarr, a coming soon video, and what to do when YouTube refuses." },
  { slug: "video-maker", group: "Advanced", summary: "Make your own intro from text, colours, a logo and music." },
  { slug: "storage", group: "Advanced", summary: "How much space Prerolls Max uses, and moving the intro folder." },
  { slug: "video-scaling", group: "Advanced", summary: "Smaller copies of intros for viewers away from home." },
  { slug: "system-updates", group: "Advanced", summary: "Your version, updates, the tools Prerolls Max uses, and diagnostics." },
  { slug: "play-history", group: "Reference", summary: "What Played: recent plays, most and least played, and intros that never played." },
  { slug: "what-servers-can-do", group: "Reference", summary: "What Plex, Jellyfin and Emby can and can't do with intros." },
  { slug: "glossary", group: "Reference", summary: "Every term used in Prerolls Max, in plain words." },
  { slug: "settings", group: "Reference", summary: "Backups, time zone, accounts and the Advanced switch." },
];

function titleOf(body: string, fallback: string): string {
  const m = /^#\s+(.+)$/m.exec(body);
  return m?.[1]?.trim() ?? fallback;
}

/** Drops the leading "# Title" line, since pages show the title themselves. */
function withoutTitle(body: string): string {
  return body.replace(/^#\s+.+\n+/, "");
}

export const ARTICLES: HelpArticle[] = META.flatMap((meta) => {
  const raw = files[`./${meta.slug}.md`];
  if (raw === undefined) return [];
  return [{ ...meta, title: titleOf(raw, meta.slug), body: withoutTitle(raw) }];
});

export function getArticle(slug: string): HelpArticle | undefined {
  return ARTICLES.find((a) => a.slug === slug);
}

export interface SearchHit {
  article: HelpArticle;
  snippet: string;
}

/** Every word must appear in the title, summary or text. Title matches rank first. */
export function searchHelp(query: string): SearchHit[] {
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  if (!words.length) return [];
  const hits: { hit: SearchHit; score: number }[] = [];
  for (const article of ARTICLES) {
    const title = article.title.toLowerCase();
    const text = `${title} ${article.summary.toLowerCase()} ${article.body.toLowerCase()}`;
    if (!words.every((w) => text.includes(w))) continue;
    const score = words.reduce((s, w) => s + (title.includes(w) ? 10 : 0) + (article.summary.toLowerCase().includes(w) ? 3 : 0), 0);
    const first = article.body.toLowerCase().indexOf(words[0] ?? "");
    // Links keep their words only: "[a playlist](help:playlists)" reads "a playlist".
    const plain = article.body
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/[#*_`>|[\]()-]/g, " ")
      .replace(/\s+/g, " ");
    const at = Math.max(0, plain.toLowerCase().indexOf(words[0] ?? "") - 60);
    const snippet = first >= 0 ? `${at > 0 ? "…" : ""}${plain.slice(at, at + 160).trim()}…` : article.summary;
    hits.push({ hit: { article, snippet }, score });
  }
  return hits.sort((a, b) => b.score - a.score).map((h) => h.hit);
}
