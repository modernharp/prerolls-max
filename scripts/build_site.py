#!/usr/bin/env python3
"""Build the Prerolls Max website (the GitHub Pages front end).

    python scripts/build_site.py --repository owner/repo --out site-output

Writes the home page, the Plex, Jellyfin and Emby pages, the download page,
FAQ, changelog, the documentation (rendered from the in-app help articles in
frontend/src/help and the longer guides in docs/features), 404.html,
sitemap.xml, robots.txt and the assets from site/. Files such as jellyfin/ and
unraid/ that other release steps put in the same folder are left alone.

Nothing here names a GitHub account: owner and repository come from
--repository (the release workflow passes GITHUB_REPOSITORY), and the version
from app/version.py. Standard library only.
"""
import argparse
import html
import json
import pathlib
import re
import shutil
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE_SRC = ROOT / "site"
HELP_DIR = ROOT / "frontend" / "src" / "help"
GUIDE_DIR = ROOT / "docs" / "features"
GROUP_ORDER = ["Start here", "Intro videos", "When they play", "Media servers", "Advanced", "Reference", "Deep dives"]


def write_lf(path: pathlib.Path, text: str) -> None:
    """Write UTF-8 with LF line endings on every platform, so builds are identical."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def attr(s: str) -> str:
    return html.escape(s, quote=True)


def slugify(text: str) -> str:
    s = re.sub(r"`", "", text.lower())
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s]+", "-", s.strip()).strip("-") or "section"


# ---------------------------------------------------------------- Markdown

LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


class Markdown:
    """The small Markdown subset the help articles use: headings, paragraphs,
    nested lists, tables, code fences, quotes, bold, italics, code and links."""

    def __init__(self, resolve, anchors=True):
        self.resolve = resolve
        self.anchors = anchors
        self.headings = []
        self._ids = set()

    def render(self, text: str) -> str:
        return self.blocks(text.replace("\r\n", "\n").split("\n"))

    @staticmethod
    def _starts_block(line: str) -> bool:
        return bool(line.startswith("```") or re.match(r"^#{1,4}\s", line) or line.lstrip().startswith("|")
                    or line.startswith(">") or LIST_RE.match(line))

    def blocks(self, lines):
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line.startswith("```"):
                j, buf = i + 1, []
                while j < n and not lines[j].startswith("```"):
                    buf.append(lines[j])
                    j += 1
                out.append("<pre><code>" + esc("\n".join(buf)) + "</code></pre>")
                i = j + 1
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", line)
            if m:
                out.append(self._heading(len(m.group(1)), m.group(2).strip()))
                i += 1
                continue
            if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
                i, table = self._table(lines, i)
                out.append(table)
                continue
            if line.startswith(">"):
                buf = []
                while i < n and lines[i].startswith(">"):
                    buf.append(re.sub(r"^>\s?", "", lines[i]))
                    i += 1
                out.append("<blockquote>" + self.blocks(buf) + "</blockquote>")
                continue
            if LIST_RE.match(line):
                i, lst = self._list(lines, i)
                out.append(lst)
                continue
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and not self._starts_block(lines[i]):
                buf.append(lines[i])
                i += 1
            out.append("<p>" + self.inline(" ".join(s.strip() for s in buf)) + "</p>")
        return "\n".join(out)

    def _heading(self, level: int, text: str) -> str:
        plain = re.sub(r"[`*]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text))
        base = slugify(plain)
        hid, k = base, 2
        while hid in self._ids:
            hid, k = f"{base}-{k}", k + 1
        self._ids.add(hid)
        if level == 2:
            self.headings.append((hid, plain))
        tag = f"h{min(level, 4)}"
        link = f'<a class="hash" href="#{hid}" aria-label="Link to this section">#</a>' if self.anchors and level in (2, 3) else ""
        return f'<{tag} id="{hid}">{self.inline(text)}{link}</{tag}>'

    def _table(self, lines, i):
        def cells(row):
            row = row.strip().strip("|")
            return [c.strip() for c in re.split(r"(?<!\\)\|", row)]
        head = cells(lines[i])
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(cells(lines[i]))
            i += 1
        h = "".join(f"<th scope=\"col\">{self.inline(c)}</th>" for c in head)
        b = "".join("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>" for r in rows)
        return i, f'<div class="table-wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

    def _list(self, lines, i):
        m = LIST_RE.match(lines[i])
        base, ordered, n = len(m.group(1)), m.group(2)[0].isdigit(), len(lines)
        items = []
        while i < n:
            m = LIST_RE.match(lines[i])
            if not m or len(m.group(1)) != base or m.group(2)[0].isdigit() != ordered:
                break
            item = [m.group(3)]
            i += 1
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and len(lines[j]) - len(lines[j].lstrip()) > base:
                        item.append("")
                        i += 1
                        continue
                    break
                ind = len(cur) - len(cur.lstrip())
                if ind > base:
                    item.append(cur)
                    i += 1
                    continue
                if LIST_RE.match(cur) or self._starts_block(cur):
                    break
                item.append(cur)
                i += 1
            deeper = [len(x) - len(x.lstrip()) for x in item[1:] if x.strip() and len(x) - len(x.lstrip()) > base]
            cut = min(deeper) if deeper else 0
            body = [item[0]] + [(x[cut:] if x.strip() and len(x) - len(x.lstrip()) > base else x.strip()) for x in item[1:]]
            inner = self.blocks(body)
            if inner.count("<p>") <= 1:
                inner = re.sub(r"^<p>(.*?)</p>", r"\1", inner, count=1, flags=re.S)
            items.append(f"<li>{inner}</li>")
        tag = "ol" if ordered else "ul"
        return i, f"<{tag}>" + "".join(items) + f"</{tag}>"

    def inline(self, s: str) -> str:
        stash = []

        def keep(h):
            stash.append(h)
            return f"\x00{len(stash) - 1}\x00"

        s = re.sub(r"`([^`]+)`", lambda m: keep("<code>" + esc(m.group(1)) + "</code>"), s)
        s = esc(s)
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: keep(self.resolve(self._emph(m.group(1)), html.unescape(m.group(2)))), s)
        s = self._emph(s)
        while "\x00" in s:
            s = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], s)
        return s

    @staticmethod
    def _emph(s: str) -> str:
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)


# ---------------------------------------------------------------- Site

def png_size(path: pathlib.Path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def ld_json(obj) -> str:
    """JSON for a script tag: the text "</" must not appear inside it."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


class Site:
    def __init__(self, repository: str):
        self.owner, self.repo = repository.split("/")
        self.owner_lc = self.owner.lower()
        self.base = f"/{self.repo}"
        self.origin = f"https://{self.owner_lc}.github.io/{self.repo}"
        self.gh = f"https://github.com/{self.owner}/{self.repo}"
        self.image = f"ghcr.io/{self.owner_lc}/prerolls-max"
        self.version = re.search(r"__version__\s*=\s*'([^']+)'", (ROOT / "app" / "version.py").read_text(encoding="utf-8")).group(1)
        self.plugin = re.search(r"<PrerollsMaxPluginVersion>([^<]+)<", (ROOT / "plugins" / "Directory.Build.props").read_text(encoding="utf-8")).group(1)
        changelog = (ROOT / "app" / "CHANGELOG.md").read_text(encoding="utf-8")
        m = re.search(r"^## \[" + re.escape(self.version) + r"\]\s*-\s*(\d{4}-\d{2}-\d{2})", changelog, re.M)
        self.date = m.group(1) if m else ""
        self.changelog = changelog
        self.rel = f"{self.gh}/releases/download/v{self.version}/"
        self.files = {
            "installer": f"PrerollsMax_Installer_v{self.version}.exe",
            "jf12": f"PrerollsMax.Jellyfin-12-{self.plugin}.zip",
            "jf1011": f"PrerollsMax.Jellyfin-10.11-{self.plugin}.zip",
            "emby": f"PrerollsMax.Emby-{self.plugin}.zip",
            "source": f"prerolls-max-{self.version}-source.zip",
            "sums": "SHA256SUMS.txt",
        }
        self.pages_out = {}      # path -> html
        self.docs = self._load_docs()
        self.warnings = []

    # ----- URLs
    def u(self, path: str) -> str:
        return f"{self.base}{path}"

    def abs(self, path: str) -> str:
        return f"{self.origin}{path}"

    def dl(self, key: str) -> str:
        return self.rel + self.files[key]

    # ----- docs sources
    def _load_docs(self):
        index = (HELP_DIR / "index.ts").read_text(encoding="utf-8")
        docs = []
        for m in re.finditer(r'\{\s*slug:\s*"([^"]+)",\s*group:\s*"([^"]+)",\s*summary:\s*"((?:[^"\\]|\\.)*)"', index):
            slug, group, summary = m.group(1), m.group(2), m.group(3).replace('\\"', '"')
            if slug == "faq":
                continue  # the website has its own FAQ page: /faq/
            f = HELP_DIR / f"{slug}.md"
            if not f.exists():
                continue
            raw = f.read_text(encoding="utf-8")
            title = re.search(r"^#\s+(.+)$", raw, re.M).group(1).strip()
            docs.append({"kind": "help", "slug": slug, "group": group, "summary": summary, "title": title,
                         "body": re.sub(r"^#\s+.+\n+", "", raw, count=1), "path": f"/docs/{slug}/"})
        for f in sorted(GUIDE_DIR.glob("*.md")):
            raw = f.read_text(encoding="utf-8")
            title = re.search(r"^#\s+(.+)$", raw, re.M).group(1).strip()
            first = next((p for p in re.split(r"\n\s*\n", re.sub(r"^#\s+.+\n+", "", raw, count=1)) if p.strip() and not p.lstrip().startswith(("#", "-", "|", ">", "```"))), "")
            summary = re.sub(r"\s+", " ", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"[`*]", "", first))).strip()
            if len(summary) > 190:
                summary = summary[:187].rsplit(" ", 1)[0] + "..."
            docs.append({"kind": "guide", "slug": f.stem, "group": "Deep dives", "summary": summary, "title": title,
                         "body": re.sub(r"^#\s+.+\n+", "", raw, count=1), "path": f"/docs/guides/{f.stem}/"})
        return docs

    def md_link(self, label: str, href: str) -> str:
        if href.startswith("help:"):
            slug = href[5:]
            if slug == "faq":
                return f'<a href="{self.u("/faq/")}">{label}</a>'
            if any(d["kind"] == "help" and d["slug"] == slug for d in self.docs):
                return f'<a href="{self.u(f"/docs/{slug}/")}">{label}</a>'
        elif href.startswith("app:"):
            return f'<span class="ui">{label}</span>'
        elif href.startswith(("http://", "https://")):
            return f'<a href="{attr(href)}" rel="noopener">{label}</a>'
        elif href.startswith("#"):
            return f'<a href="{attr(href)}">{label}</a>'
        else:
            m = re.match(r"^([\w-]+)\.md(#[\w-]+)?$", href)
            if m and any(d["kind"] == "guide" and d["slug"] == m.group(1) for d in self.docs):
                return f'<a href="{self.u(f"/docs/guides/{m.group(1)}/")}{m.group(2) or ""}">{label}</a>'
        self.warnings.append(f"unresolved link {href!r}")
        return label

    # ----- chrome
    def head(self, title, desc, path, *, schema=(), og="/assets/img/social-preview.png", noindex=False):
        canonical = self.abs(path)
        robots = "noindex,follow" if noindex else "index,follow,max-image-preview:large"
        ld = "".join('<script type="application/ld+json">' + ld_json(obj) + "</script>\n" for obj in schema)
        t, d = attr(title), attr(desc)
        return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{d}">
<meta name="robots" content="{robots}">
<meta name="theme-color" content="#14103a">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{self.u('/assets/icons/favicon.ico')}" sizes="any">
<link rel="icon" href="{self.u('/assets/icons/logo.svg')}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{self.u('/assets/icons/apple-touch-icon.png')}">
<link rel="preload" href="{self.u('/assets/fonts/oswald.woff2')}" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{self.u('/assets/fonts/lora.woff2')}" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{self.u('/assets/site.css')}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Prerolls Max">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{self.abs(og)}">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta property="og:image:alt" content="Prerolls Max: intro videos before your movies, for Plex, Jellyfin and Emby">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{self.abs(og)}">
{ld}</head>
"""

    def header(self, path):
        def a(href, text):
            cur = ' aria-current="page"' if (path == href or (href != "/" and path.startswith(href))) else ""
            return f'<a href="{self.u(href)}"{cur}>{text}</a>'
        return f"""<body>
<a class="skip" href="#main">Skip to the content</a>
<header class="site-header"><div class="wrap">
<a class="brand" href="{self.u('/')}"><img src="{self.u('/assets/icons/icon-192.png')}" alt="" width="30" height="30">Prerolls Max</a>
<nav aria-label="Main">{a('/download/', 'Download')}{a('/plex/', 'Plex')}{a('/jellyfin/', 'Jellyfin')}{a('/emby/', 'Emby')}{a('/docs/', 'Docs')}{a('/faq/', 'FAQ')}<a href="{self.gh}" rel="noopener">GitHub</a></nav>
</div></header>
"""

    def footer(self):
        return f"""<footer class="site-footer"><div class="wrap">
<div><h2>Prerolls Max</h2><p>Intro videos before your movies, for Plex, Jellyfin and Emby. Version {esc(self.version)}.</p></div>
<div><h2>Get it</h2><ul><li><a href="{self.u('/download/')}">Download</a></li><li><a href="{self.u('/changelog/')}">What's new</a></li><li><a href="{self.gh}/releases" rel="noopener">All releases</a></li></ul></div>
<div><h2>Set it up</h2><ul><li><a href="{self.u('/plex/')}">Plex</a></li><li><a href="{self.u('/jellyfin/')}">Jellyfin</a></li><li><a href="{self.u('/emby/')}">Emby</a></li><li><a href="{self.u('/docs/moving-from-nexroll/')}">Moving from NeXroll</a></li></ul></div>
<div><h2>Help</h2><ul><li><a href="{self.u('/docs/')}">Documentation</a></li><li><a href="{self.u('/faq/')}">FAQ</a></li><li><a href="{self.u('/docs/intro-not-playing/')}">My intro isn't playing</a></li><li><a href="{self.gh}/issues/new/choose" rel="noopener">Report a problem</a></li></ul></div>
<p class="legal">Free for personal and other noncommercial use under the <a href="{self.gh}/blob/main/LICENSE" rel="noopener">PolyForm Noncommercial License 1.0.0</a>. Built on <a href="https://github.com/JFLXCLOUD/NeXroll" rel="noopener">NeXroll</a> by JFLXCLOUD. Community intros come from <a href="https://www.prerolls.me" rel="noopener">Prerolls.me</a> and <a href="https://typicalnerds.uk" rel="noopener">Prerolls.uk</a>. Plex, Jellyfin and Emby are trademarks of their owners; Prerolls Max is not affiliated with them.</p>
</div></footer>
<script src="{self.u('/assets/site.js')}" defer></script>
</body>
</html>
"""

    def crumbs(self, trail):
        """trail: [(name, path), ...] ending at the current page. Returns (html, schema)."""
        parts, items = [], [("Home", "/")] + list(trail)
        for k, (name, p) in enumerate(items):
            parts.append(f'<a href="{self.u(p)}">{esc(name)}</a>' if k < len(items) - 1 else esc(name))
        schema = {"@context": "https://schema.org", "@type": "BreadcrumbList",
                  "itemListElement": [{"@type": "ListItem", "position": k + 1, "name": n, "item": self.abs(p)} for k, (n, p) in enumerate(items)]}
        return '<p class="crumbs">' + " / ".join(parts) + "</p>", schema

    def add(self, path, html_text):
        self.pages_out[path] = html_text

    def inner_page(self, path, title, desc, h1, lead, body, trail, *, schema=(), aside=""):
        crumb_html, crumb_ld = self.crumbs(trail)
        text = self.head(title, desc, path, schema=[crumb_ld, *schema]) + self.header(path)
        text += f'<main id="main">\n<div class="page-head"><div class="wrap">{crumb_html}<h1>{esc(h1)}</h1>{f"<p>{lead}</p>" if lead else ""}</div></div>\n'
        if aside:
            body = f'<div class="cols"><div>{body}</div><aside class="aside" aria-label="At a glance">{aside}</aside></div>'
        text += f'<div class="wrap page">{body}</div>\n</main>\n' + self.footer()
        self.add(path, text)

    def software_ld(self):
        shots = [self.abs(f"/assets/img/{n}.png") for n in ("home", "intro-videos", "schedule-wizard", "calendar", "rules", "media-servers")]
        return {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Prerolls Max",
                "url": self.abs("/"), "image": self.abs("/assets/img/social-preview.png"),
                "description": "Play short intro videos (prerolls) before movies on Plex, Jellyfin and Emby. Choose the videos and set when each one plays.",
                "applicationCategory": "MultimediaApplication",
                "operatingSystem": "Windows 10, Windows 11, Linux (Docker), Unraid",
                "softwareVersion": self.version, "datePublished": self.date or None,
                "downloadUrl": self.dl("installer"), "license": "https://polyformproject.org/licenses/noncommercial/1.0.0/",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                "screenshot": shots, "isBasedOn": "https://github.com/JFLXCLOUD/NeXroll",
                "codeRepository": self.gh}

    @staticmethod
    def faq_ld(items):
        return {"@context": "https://schema.org", "@type": "FAQPage",
                "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}} for q, a in items]}

    def steps(self, items):
        return '<ol class="steplist">' + "".join(f"<li><h3>{t}</h3>{b}</li>" for t, b in items) + "</ol>"

    def faq_block(self, items):
        return '<div class="faq">' + "".join(
            f'<details><summary>{esc(q)}</summary><div class="answer">{a}</div></details>' for q, a in items) + "</div>"

    def img(self, name, alt, *, lazy=True, cls="shot", sizes=None, hi=False):
        w, h = png_size(SITE_SRC / "assets" / "img" / f"{name}.png")
        w, h = w // 2, h // 2
        extra = ' fetchpriority="high"' if hi else (' loading="lazy"' if lazy else "")
        return f'<img class="{cls}" src="{self.u(f"/assets/img/{name}.png")}" alt="{attr(alt)}" width="{w}" height="{h}"{extra} decoding="async">'


# ---------------------------------------------------------------- Content

def faq_items(s: Site):
    nex = s.u("/docs/moving-from-nexroll/")
    return [
        ("Is Prerolls Max free?",
         "<p>Yes, for use at home and other noncommercial purposes. The licence is PolyForm Noncommercial 1.0.0, which does not allow selling it or using it to make money. The source code is public on GitHub.</p>"),
        ("What is a preroll?",
         "<p>A short video that plays before the movie, like the clips a cinema shows before the main film. Plex calls the setting Cinema Trailers. Jellyfin and Emby call them intros.</p>"),
        ("Which media servers does it work with?",
         f'<p>Plex, Jellyfin and Emby, and you can connect more than one at once. Plex needs no plugin. Jellyfin (10.11 and 12) and Emby (4.9 and later) use a small Prerolls Max plugin. See the pages for <a href="{s.u("/plex/")}">Plex</a>, <a href="{s.u("/jellyfin/")}">Jellyfin</a> and <a href="{s.u("/emby/")}">Emby</a>.</p>'),
        ("Do I need Plex Pass?",
         "<p>No. Plex plays your own intro videos without Plex Pass.</p>"),
        ("Do I need Emby Premiere?",
         "<p>Yes. Emby plays intros through its Cinema Intros feature, and that needs Emby Premiere.</p>"),
        ("Where does it run?",
         f'<p>On your own computer or NAS: a Windows 10 or 11 PC with the installer, or any machine that runs Docker (including Unraid, Synology and Raspberry Pi). Your intro videos stay in a folder you choose. <a href="{s.u("/download/")}">Download options</a>.</p>'),
        ("Why does everyone get the same intro on Plex?",
         "<p>Plex has one intro list for the whole server, not one per person. Prerolls Max changes that list when a schedule starts or ends. If two people start a movie at the same time, they get intros from the same list. Jellyfin and Emby pick an intro for each play.</p>"),
        ("Can intros play before TV episodes?",
         "<p>On Jellyfin and Emby, yes, with the Prerolls Max plugin. They play before the episode you pick, not between episodes that follow each other on their own. On Plex, no: Plex plays intros before movies only.</p>"),
        ("Can I play a different intro for each genre, age rating or person?",
         f'<p>On Jellyfin and Emby, yes, with <a href="{s.u("/docs/rules/")}">rules</a>. The right intro is picked for each play. On Plex, no: Plex picks its intro before it knows which movie is starting.</p>'),
        ("Why didn't the intro play when I carried on watching?",
         "<p>No media server plays an intro when you resume a movie. Start it from the beginning and the intro plays.</p>"),
        ("Which video format should I use?",
         "<p>MP4 with H.264 video and AAC sound plays everywhere. Most intros run 10 to 30 seconds. If an intro is 4K or HDR and your movies are not, make a TV-friendly version in Prerolls Max.</p>"),
        ("Why does my Roku play only the first intro?",
         f'<p>The official Jellyfin app on Roku plays only the first intro in the list. <a href="{s.u("/docs/media-tools/")}">Combine your intros into one video</a> and it plays them all.</p>'),
        ("I use NeXroll. Can I keep my setup?",
         f'<p>Yes. Prerolls Max replaces NeXroll and brings your schedules, collections and settings across. Stop NeXroll first: both use port 9393 and both would change the same media servers. <a href="{nex}">Step-by-step guide</a>.</p>'),
        ("My intro isn't playing. What do I check?",
         f'<p>Play a movie from the beginning in a web browser first. If the intro plays there, your setup works and the app on your TV or phone is the reason. <a href="{s.u("/docs/intro-not-playing/")}">The full checklist</a> covers each case, most common first.</p>'),
    ]


def build_home(s: Site):
    faqs = faq_items(s)
    home_faqs = [faqs[i] for i in (0, 1, 2, 6, 12, 13)]
    shot = s.img("home", "The Prerolls Max Home page: servers connected, what plays now and what plays next", lazy=False, cls="", hi=True)
    head_html = s.head("Prerolls Max: intro videos for Plex, Jellyfin and Emby",
        "Play a short intro before movies on Plex, Jellyfin or Emby. Choose the videos, set when each one plays, and run it on your own PC or NAS. Free for home use.",
        "/", schema=[s.software_ld(), s.faq_ld(home_faqs), {"@context": "https://schema.org", "@type": "WebSite", "name": "Prerolls Max", "url": s.abs("/")}])
    body = f"""{head_html}{s.header("/")}
<main id="main">
<section class="hero"><div class="wrap">
<div>
<h1>Play an intro before every movie.</h1>
<p class="lead">Prerolls Max runs next to your media server. You pick the videos and say when each one plays: Halloween intros all October, a kids' intro before anything rated PG, a cinema pre-show on Friday night.</p>
<div class="btnrow"><a class="btn" href="{s.dl('installer')}">Download for Windows</a><a class="btn ghost" href="{s.u('/download/#docker')}">Run it with Docker</a></div>
<p class="fine">Version {esc(s.version)} for Plex, Jellyfin and Emby. Free for home use. <a href="{s.u('/download/')}">All downloads</a></p>
</div>
<div class="stage">
<div class="leader" aria-hidden="true"><svg viewBox="0 0 160 100" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#3f3a8f" stroke-width="0.7"><circle cx="80" cy="50" r="34"/><circle cx="80" cy="50" r="42"/><path d="M0 50H160M80 0V100"/></g></svg><div class="sweep"></div><div class="num"><span>3</span><span>2</span><span>1</span></div></div>
<figure class="screen">{shot}</figure>
</div>
</div></section>

<section class="alt" id="schedules"><div class="wrap">
<div class="sec-head"><h2>You decide when each intro plays</h2><p>A schedule is a set of intros plus a time. When two overlap, you choose which one wins, and a calendar shows what plays on every day.</p></div>
<ul class="program">
<li><span class="when">All of October</span><span class="what"><b>Halloween intros.</b> Pick dates, days of the week, or a holiday. Moving ones like Easter are built in.</span></li>
<li><span class="when">Anything rated PG</span><span class="what"><b>A kids' intro.</b> Rules choose by genre, age rating, decade, library or person on Jellyfin and Emby.</span></li>
<li><span class="when">Friday night</span><span class="what"><b>A cinema-style pre-show.</b> Pick days of the week and times of day.</span></li>
<li><span class="when">Horror from the 1980s</span><span class="what"><b>An 80s horror intro.</b> A rule can match a decade and a genre together. Press Try it to check a title.</span></li>
<li><span class="when">Everything else</span><span class="what"><b>Your default intros.</b> They play when no schedule is on, so no movie starts bare.</span></li>
</ul>
</div></section>

<section id="how"><div class="wrap">
<div class="sec-head"><h2>Up and running in three steps</h2><p>Most people are done in under half an hour. The app walks you through each step and checks it worked.</p></div>
<ol class="steps">
<li><h3>Install it</h3><p>Run the Windows installer, or start the Docker image on a NAS, Unraid or Linux machine. It opens as a web page at port 9393.</p></li>
<li><h3>Connect your server</h3><p>On Plex you sign in and you're done. Jellyfin and Emby also need a small plugin, and the app downloads the right one for your version.</p></li>
<li><h3>Pick videos and times</h3><p>Add your own videos or get free ones from Prerolls.me and Prerolls.uk. Then press Play a test and watch it play before a movie.</p></li>
</ol>
</div></section>

<section class="alt" id="features"><div class="wrap">
<div class="sec-head"><h2>What's inside</h2></div>
<div class="row"><div class="copy-col"><h3>Your videos, in collections</h3><p>Drop in files or paste a link. Group them into collections like "Everyday" and "Halloween", and let Prerolls Max even out the loudness so no intro is far louder than the rest. MP4 plays on every server.</p></div>{s.img("intro-videos", "The Intro Videos page: a grid of intro videos sorted into collections")}</div>
<div class="row flip"><div class="copy-col"><h3>Free intros, with credit</h3><p>Browse Prerolls.me and Prerolls.uk without leaving the app. Each video names the person who made it. YouTube and Vimeo videos open as links and are never downloaded.</p></div>{s.img("community", "The Community page listing free intros from Prerolls.me and Prerolls.uk")}</div>
<div class="row"><div class="copy-col"><h3>Schedules in three steps</h3><p>Choose the collection, choose when, and decide what happens when two schedules overlap. A sentence on the right says what will happen, in plain words, before you save.</p></div>{s.img("schedule-wizard", "The new schedule wizard with a sentence describing what will happen", cls="shot crop")}</div>
<div class="row flip"><div class="copy-col"><h3>The whole year on a calendar</h3><p>See which schedule plays on each day and which one wins when they overlap. Halloween, Christmas and your everyday intros each get their own colour.</p></div>{s.img("calendar", "The month calendar showing Halloween, Everyday and Christmas schedules", cls="shot crop")}</div>
<div class="row"><div class="copy-col"><h3>Rules for Jellyfin and Emby</h3><p>Pick a different intro by genre, age rating, decade, library or person. Keep a never-play list. Play intros only before the first episode of a binge. Try it shows which rule would match a title, and why.</p></div>{s.img("rules", "The Rules page with a kids-safe rule and the Try it box showing a match", cls="shot crop")}</div>
<div class="row flip"><div class="copy-col"><h3>All three servers, side by side</h3><p>Plex, Jellyfin and Emby each get a card that shows whether the connection and the plugin are working. Next to every option, a badge tells you what that server can do.</p></div>{s.img("media-servers", "The Media Servers page with Plex, Jellyfin and Emby cards", cls="shot crop")}</div>
<div class="row"><div class="copy-col"><h3>Help for when an intro doesn't play</h3><p>A troubleshooter asks which server and app you use and checks your setup as you answer. Home also warns you when a movie started without its intro. The guides are built in and work offline.</p></div>{s.img("help", "The troubleshooter asking which app you use and checking the setup", cls="shot crop")}</div>
<div class="row flip"><div class="copy-col"><h3>Dark mode, and your phone</h3><p>The app follows your system's light or dark setting. On a phone the same pages fit the screen, with a tab bar at the bottom.</p></div><div class="pair">{s.img("dark-home", "Home in dark mode")}{s.img("phone", "Home on a phone")}</div></div>
</div></section>

<section id="servers"><div class="wrap">
<div class="sec-head"><h2>What each media server can do</h2><p>The three servers handle intros differently. Prerolls Max works around the limits where it can, and tells you where it can't.</p></div>
<div class="table-wrap"><table>
<thead><tr><th scope="col"></th><th scope="col"><a href="{s.u('/plex/')}">Plex</a></th><th scope="col"><a href="{s.u('/jellyfin/')}">Jellyfin</a></th><th scope="col"><a href="{s.u('/emby/')}">Emby</a></th></tr></thead>
<tbody>
<tr><th scope="row">Plugin needed</th><td>No</td><td>Yes, Prerolls Max Intros</td><td>Yes, Prerolls Max Intros</td></tr>
<tr><th scope="row">Costs extra</th><td>No</td><td>No</td><td>Emby Premiere</td></tr>
<tr><th scope="row">Intros before movies</th><td class="yes">Yes</td><td class="yes">Yes</td><td class="yes">Yes</td></tr>
<tr><th scope="row">Intros before TV episodes</th><td class="no">No</td><td class="yes">Yes</td><td class="yes">Yes</td></tr>
<tr><th scope="row">Intro picked for each play</th><td class="no">No, one list for the server</td><td class="yes">Yes</td><td class="yes">Yes</td></tr>
<tr><th scope="row">Rules by genre, rating or person</th><td class="no">No</td><td class="yes">Yes</td><td class="yes">Yes</td></tr>
<tr><th scope="row">Intro when you resume</th><td class="no">No</td><td class="no">No</td><td class="no">No</td></tr>
</tbody></table></div>
<p class="meta">Which apps play intros varies too. Each page below lists them. <a href="{s.u('/docs/devices/')}">Which apps play intros</a>.</p>
</div></section>

<section class="alt" id="nexroll"><div class="wrap"><div class="read">
<h2>Coming from NeXroll?</h2>
<p style="margin-top:.8rem">Prerolls Max started as a fork of NeXroll 2.4.0 and replaces it. Run one or the other, not both: Plex has one intro list per server and both apps would keep overwriting it, and on Jellyfin and Emby every movie would get two sets of intros.</p>
<p>Your schedules, collections and settings can come across. Open Settings, then Moving from NeXroll, and Prerolls Max reads NeXroll's data folder, a backup file, or a NeXroll that's still running. It shows what it found before it changes anything.</p>
<p><a class="btn" href="{s.u('/docs/moving-from-nexroll/')}">Read the moving guide</a></p>
</div></div></section>

<section id="faq"><div class="wrap"><div class="sec-head"><h2>Questions people ask</h2></div>
{s.faq_block(home_faqs)}
<p style="margin-top:1.4rem"><a href="{s.u('/faq/')}">More questions and answers</a></p>
</div></section>

<section class="cta-band"><div class="wrap">
<h2>Try it tonight</h2>
<p>Download Prerolls Max {esc(s.version)} for Windows, or run the Docker image. Then press Play a test.</p>
<div class="btnrow"><a class="btn" href="{s.dl('installer')}">Download for Windows</a><a class="btn ghost" href="{s.u('/download/')}">Docker, Unraid and plugins</a></div>
</div></section>
</main>
""" + s.footer()
    s.add("/", body)


def build_download(s: Site):
    pull = f"docker pull {s.image}:latest"
    run = (f"docker run -d --name prerollsmax --restart unless-stopped -p 9393:9393 \\\n  -e TZ=Europe/London -e PUID=1000 -e PGID=1000 \\\n"
           f"  -v prerollsmax-data:/data \\\n  -v /path/to/your/prerolls:/data/prerolls \\\n  {s.image}:latest")
    ver_page = f"{s.gh}/releases/tag/v{s.version}"
    rows = [
        ("Windows", "Windows 10 or 11, 64-bit. Asks where to install and where to keep your intros. Can install FFmpeg, run as a service and open the firewall port.",
         s.dl("installer"), "Download .exe"),
        ("Jellyfin 12 plugin", "Zip for Jellyfin 12. Easier: add the plugin repository below and install from the Jellyfin catalog.", s.dl("jf12"), "Download .zip"),
        ("Jellyfin 10.11 plugin", "Zip for Jellyfin 10.11. Easier: add the plugin repository below.", s.dl("jf1011"), "Download .zip"),
        ("Emby plugin", "For Emby 4.9 and later. Unzip it and put PrerollsMax.Emby.dll in Emby's plugins folder.", s.dl("emby"), "Download .zip"),
        ("Unraid template", "A ready-made container template for Unraid's Docker page.", f"{s.origin}/unraid/prerolls-max.xml", "Open template"),
    ]
    dl_rows = "".join(f'<div class="dl"><h3>{t}</h3><p>{d}</p><a class="btn" href="{attr(u)}">{b}</a></div>' for t, d, u, b in rows)
    body = f"""<p class="meta">Version {esc(s.version)}{f", released {esc(s.date)}" if s.date else ""}. Plugin version {esc(s.plugin)}. <a href="{ver_page}" rel="noopener">Release page</a>, <a href="{s.u('/changelog/')}">what's new</a>, <a href="{s.gh}/releases" rel="noopener">older releases</a>.</p>
<div class="downloads">{dl_rows}</div>

<h2 id="docker" style="margin-top:3rem">Docker</h2>
<div class="prose">
<p>The image runs on 64-bit Intel and AMD machines and on ARM (Raspberry Pi and similar). It runs as an ordinary user, not as root. <code>PUID</code> and <code>PGID</code> should be the user and group that own your intro folder. Run <code>id</code> to see yours; on Unraid they are 99 and 100.</p>
<pre><code>{esc(run)}</code></pre>
<p>Then open <code>http://&lt;your-computer&gt;:9393</code> and make an account. Prefer Compose? <a href="{s.gh}/blob/main/docker-compose.yml" rel="noopener">Download docker-compose.yml</a>, change the intro folder, and run <code>docker compose up -d</code>.</p>
<p>Image tags: <code>latest</code> follows the newest stable release, <code>{esc(s.version)}</code> stays on this version, and <code>edge</code> follows the main branch.</p>
<pre><code>{esc(pull)}</code></pre>
<p>If Plex runs in Docker too, give it the same intro folder. If it sees the folder under a different path, read <a href="{s.u('/docs/folder-mapping/')}">folder mapping</a>.</p>
</div>

<h2 id="jellyfin" style="margin-top:3rem">Jellyfin plugin repository</h2>
<div class="prose">
<p>In Jellyfin, open Dashboard, Plugins, Repositories, press <span class="ui">+</span>, name it Prerolls Max and paste the address for your version. Then open Catalog, install Prerolls Max Intros, and restart Jellyfin.</p>
<pre><code>Jellyfin 12:    {esc(s.origin)}/jellyfin/manifest.json
Jellyfin 10.11: {esc(s.origin)}/jellyfin/manifest-10.11.json</code></pre>
<p>Full steps: <a href="{s.u('/jellyfin/')}">Prerolls Max on Jellyfin</a>.</p>
</div>

<h2 id="verify" style="margin-top:3rem">Check your download</h2>
<div class="prose">
<p>Every file is listed with its SHA-256 checksum in <a href="{s.dl('sums')}">SHA256SUMS.txt</a> on the release. To check a file on Windows, run this in PowerShell and compare the result with the line for that file:</p>
<pre><code>Get-FileHash .\\{esc(s.files['installer'])} -Algorithm SHA256</code></pre>
<p>On Linux or macOS, put the file next to SHA256SUMS.txt and run <code>sha256sum -c SHA256SUMS.txt --ignore-missing</code>.</p>
<p>The Windows installer is not signed with a paid code-signing certificate, so Windows SmartScreen may say it protected your PC. Choose <span class="ui">More info</span>, then <span class="ui">Run anyway</span>, once you've compared the checksum.</p>
</div>

<h2 id="source" style="margin-top:3rem">Source code</h2>
<div class="prose"><p>The source is on <a href="{s.gh}" rel="noopener">GitHub</a>, or as a <a href="{s.dl('source')}">zip for version {esc(s.version)}</a>. Prerolls Max is released under the <a href="{s.gh}/blob/main/LICENSE" rel="noopener">PolyForm Noncommercial License 1.0.0</a>.</p></div>

<h2 id="requirements" style="margin-top:3rem">What you need</h2>
<div class="prose"><ul>
<li><strong>Plex:</strong> any recent Plex Media Server. No Plex Pass.</li>
<li><strong>Jellyfin:</strong> 10.11 or 12, with the Prerolls Max plugin.</li>
<li><strong>Emby:</strong> 4.9 or later, with the plugin and Emby Premiere.</li>
<li><strong>FFmpeg</strong> for checking and fixing videos. The Windows installer can add it, and the Docker image has it.</li>
</ul></div>
"""
    s.inner_page("/download/", "Download Prerolls Max: Windows, Docker, Unraid, Jellyfin, Emby",
                 f"Download Prerolls Max {s.version} for Windows, Docker or Unraid, plus the Jellyfin and Emby plugins. Direct links, checksums and install steps.",
                 f"Download Prerolls Max {s.version}", "Pick the one that matches how you run your media server. Every file here is the same one attached to the release on GitHub.",
                 body, [("Download", "/download/")], schema=[s.software_ld()])


def server_steps_common(s: Site):
    return {
        "key": f'<p>In Prerolls Max, press <span class="ui">Test connection</span> on the server card. Each check gets a tick, or tells you what to fix.</p>',
        "test": f'<p>On Home, press <span class="ui">Start test</span> next to Play a test, then start a movie from the beginning in a web browser. Your intro should play first. Test in a browser before a TV or phone: some apps skip intros until you change a setting. See <a href="{s.u("/docs/devices/")}">which apps play intros</a>.</p>',
    }


def build_plex(s: Site):
    c = server_steps_common(s)
    faq = [
        ("Does Plex need a plugin for prerolls?", "<p>No. Prerolls Max fills in Plex's own Cinema Trailers setting and keeps it up to date.</p>"),
        ("Do I need Plex Pass?", "<p>No. Plex plays your own intro videos without Plex Pass.</p>"),
        ("Can Plex play a different intro for each movie or person?", "<p>No. Plex has one intro list for the whole server and picks the intro before it knows which movie is starting. Prerolls Max changes the list when a schedule starts or ends, which works well for dates and holidays. For choices by genre, rating or person, use Jellyfin or Emby.</p>"),
        ("Why are there no intros before TV episodes on Plex?", "<p>Plex plays intros before movies only. This is a Plex limit, not a setting.</p>"),
        ("Why can't Plex find my intro files?", f'<p>Prerolls Max sends Plex the path to each file, and Plex opens the file itself. In Docker the two may see the folder under different paths. <a href="{s.u("/docs/folder-mapping/")}">Folder mapping</a> fixes it, with a full example.</p>'),
    ]
    steps_html = s.steps([
 ("Install Prerolls Max", f'<p>Use the <a href="{s.u("/download/")}">Windows installer or the Docker image</a>, open it in a browser at port 9393, and make your admin account.</p>'),
 ("Sign in with Plex", '<p>Open Media Servers and press <span class="ui">Connect Plex</span>, then <span class="ui">Sign in with Plex</span>. A Plex window opens. Your password goes to Plex, never to Prerolls Max. Come back and Prerolls Max finds your server.</p><p>If no window opens, your browser blocked the pop-up: press <span class="ui">Open the Plex sign-in page</span> instead. You can also connect with the server address and a token under Other ways to connect.</p>'),
 ("Turn on the Plex settings", '<p>Enable Cinema Trailers in each movie library: edit the library, open Advanced. In each Plex app, Cinema trailers to play before movies must not be 0. On the 2026 Plex apps for Apple TV, iPhone, iPad, Android TV and Fire TV, set it to 1, or those apps skip intros.</p>'),
 ("Add videos and choose when they play", f'<p>Add your own intros or get free ones in Intro Videos, put them in collections, then press New schedule under When They Play. Turn on default intros so a movie never starts without one. <a href="{s.u("/docs/getting-started/")}">Getting started</a> covers each step.</p>'),
 ("Test it", c["test"]),
])
    body = f"""<div class="prose">
<p>Plex has a setting for intro videos called Cinema Trailers, but it takes one fixed list. To change an intro for Halloween, you'd edit that list by hand and remember to change it back. Prerolls Max edits it for you. When a schedule starts or ends, the list changes.</p>
<div class="callout"><h3>What you need</h3><p>Plex Media Server, Prerolls Max running, and your intro videos in a folder Plex can open. No Plex Pass and no plugin.</p></div>
<h2 id="setup">Set it up</h2></div>
{steps_html}
<div class="prose">
<h2 id="limits">What Plex can and can't do</h2>
<ul>
<li>Plex plays intros before movies only, never before TV episodes.</li>
<li>Plex has one intro list for the whole server. Everyone watching at the same time gets intros from the same list.</li>
<li>Intros don't play when you resume a movie.</li>
<li>Casting, DLNA, Plexamp, downloads and Infuse never play intros.</li>
</ul>
<h2 id="apps">Which Plex apps play intros</h2>
<div class="table-wrap"><table><thead><tr><th scope="col">App</th><th scope="col">Plays intros?</th></tr></thead><tbody>
<tr><td>Web browser (app.plex.tv), Plex desktop app</td><td>Yes</td></tr>
<tr><td>Roku, smart TVs</td><td>Usually</td></tr>
<tr><td>2026 apps for Apple TV, iPhone, iPad, Android TV, Fire TV and Shield</td><td>Only after a change: set Cinema trailers to play before movies to 1 in the app's settings</td></tr>
<tr><td>Casting, DLNA, Plexamp, downloads, Infuse</td><td>No</td></tr>
</tbody></table></div>
<p class="meta">Checked November 2026. If your app isn't listed, test in a web browser first.</p>
<h2 id="help">More help</h2>
<ul>
<li><a href="{s.u('/docs/connect-plex/')}">Connecting Plex</a>, in full</li>
<li><a href="{s.u('/docs/intro-not-playing/')}">My intro isn't playing</a></li>
<li><a href="{s.u('/docs/folder-mapping/')}">Folder mapping for Docker</a></li>
<li><a href="{s.u('/docs/what-servers-can-do/')}">What each server can do</a></li>
</ul>
<h2 id="faq">Plex questions</h2></div>
{s.faq_block(faq)}"""
    aside = (f'<h2>At a glance</h2><dl><dt>Plugin</dt><dd>None needed</dd><dt>Plex Pass</dt><dd>Not needed</dd><dt>Intros play before</dt><dd>Movies only</dd><dt>Picked</dt><dd>When a schedule starts or ends</dd></dl>'
             f'<a class="btn" href="{s.u("/download/")}">Download Prerolls Max</a>')
    s.inner_page("/plex/", "Plex prerolls: schedule intro videos with Prerolls Max",
                 "Set up intro videos (prerolls) on Plex. No plugin and no Plex Pass: Prerolls Max updates Plex's Cinema Trailers list when a schedule starts or ends.",
                 "Intro videos on Plex", "No plugin, no Plex Pass. Prerolls Max keeps Plex's own intro list up to date.", body,
                 [("Plex", "/plex/")], schema=[s.faq_ld(faq)], aside=aside)


def build_jellyfin(s: Site):
    faq = [
        ("Does Jellyfin need a plugin for prerolls?", "<p>Yes. Jellyfin has no setting of its own for intro videos. The Prerolls Max Intros plugin asks Prerolls Max which intro to play each time a movie or episode starts.</p>"),
        ("Which Jellyfin versions work?", "<p>Jellyfin 10.11 and Jellyfin 12. Prerolls Max picks the right plugin for your version.</p>"),
        ("Can Jellyfin play intros before TV episodes?", "<p>Yes. They play before the episode you pick, not between episodes that follow each other on their own. You can also limit them to the first episode of a binge.</p>"),
        ("Why does my Roku play only the first intro?", f'<p>The official Jellyfin app on Roku plays only the first intro. <a href="{s.u("/docs/media-tools/")}">Combine several intros into one video</a> and it plays them all.</p>'),
        ("Will it slow down playback?", "<p>No. The plugin waits at most 3 seconds for Prerolls Max, downloads intros in the background, and keeps playing the last list it received if Prerolls Max is down.</p>"),
    ]
    c = server_steps_common(s)
    steps_html = s.steps([
 ("Make an API key in Jellyfin", '<p>Sign in as an administrator, open Dashboard, then API Keys, press <span class="ui">+</span>, call it Prerolls Max, and copy the key.</p>'),
 ("Connect Prerolls Max to Jellyfin", '<p>In Prerolls Max, open Media Servers and press <span class="ui">Connect Jellyfin</span>. Enter the address you use to open Jellyfin, like <code>http://192.168.1.10:8096</code>, and paste the key. If Prerolls Max runs in Docker, use the computer\'s network address, not <code>localhost</code>.</p>'),
 ("Install the plugin", f'<p>Easiest: in Jellyfin, open Dashboard, Plugins, Repositories, press <span class="ui">+</span>, name it Prerolls Max, and paste the address for your version:</p><pre><code>Jellyfin 12:    {esc(s.origin)}/jellyfin/manifest.json\nJellyfin 10.11: {esc(s.origin)}/jellyfin/manifest-10.11.json</code></pre><p>Open Catalog, install Prerolls Max Intros, and restart Jellyfin.</p><p>Or install by hand: Prerolls Max can download the right zip for you, or take <a href="{s.dl("jf12")}">Jellyfin 12</a> or <a href="{s.dl("jf1011")}">Jellyfin 10.11</a> from the release. Unzip it into a new folder called <code>PrerollsMax</code> inside Jellyfin\'s plugins folder (<code>/config/plugins</code> in Docker, <code>/var/lib/jellyfin/plugins</code> on Linux, <code>%LOCALAPPDATA%\\jellyfin\\plugins</code> on Windows) and restart.</p>'),
 ("Let Prerolls Max set up the plugin", '<p>Press <span class="ui">Set up the plugin for me</span> on the Jellyfin card. Prerolls Max fills in the plugin\'s settings, including a key of its own. Then play any movie in Jellyfin and press <span class="ui">Check now</span>. The card shows Working once the plugin has asked for an intro.</p>'),
 ("Test it", c["test"]),
])
    body = f"""<div class="prose">
<p>Jellyfin has no built-in setting for intro videos. The Prerolls Max Intros plugin fills the gap: each time a movie or episode starts, it asks Prerolls Max which intro to play. That's how Jellyfin can pick a different intro by genre, age rating, decade, library or person.</p>
<div class="callout"><h3>What you need</h3><p>Jellyfin 10.11 or 12, Prerolls Max running, and an administrator account on Jellyfin.</p></div>
<h2 id="setup">Set it up</h2></div>
{steps_html}
<div class="prose">
<h2 id="apps">Which Jellyfin apps play intros</h2>
<div class="table-wrap"><table><thead><tr><th scope="col">App</th><th scope="col">Plays intros?</th></tr></thead><tbody>
<tr><td>Web browser, Jellyfin Media Player</td><td>Yes, movies and episodes</td></tr>
<tr><td>Android, Kodi (Jellyfin add-ons)</td><td>Yes</td></tr>
<tr><td>Android TV</td><td>Movies only, from the start</td></tr>
<tr><td>Roku (official app)</td><td>Turn on Cinema Mode. Plays only the first intro.</td></tr>
<tr><td>Swiftfin, Infuse, Jellyfin MPV Shim, Samsung TV</td><td>No</td></tr>
</tbody></table></div>
<p>In the apps that play intros, Cinema Mode is on to begin with and each device has its own switch. If one device skips intros, check it is still on. Intros never play when you resume a movie.</p>
<h2 id="plugin">How the plugin behaves</h2>
<ul>
<li>It never holds up playback. It waits at most 3 seconds for Prerolls Max, and intros that aren't downloaded yet keep downloading in the background.</li>
<li>It keeps working if Prerolls Max is down, by playing the last list of intros it received.</li>
<li>It tidies up after itself: a scheduled task downloads what could play and removes old copies.</li>
</ul>
<h2 id="help">More help</h2>
<ul>
<li><a href="{s.u('/docs/connect-jellyfin/')}">Connecting Jellyfin</a>, in full</li>
<li><a href="{s.u('/docs/rules/')}">Rules: different intros for different titles</a></li>
<li><a href="{s.u('/docs/intro-not-playing/')}">My intro isn't playing</a></li>
<li>Moving from NeXroll? Remove its NeXroll Intros plugin once Prerolls Max shows Working. <a href="{s.u('/docs/moving-from-nexroll/')}">Guide</a></li>
</ul>
<h2 id="faq">Jellyfin questions</h2></div>
{s.faq_block(faq)}"""
    aside = (f'<h2>At a glance</h2><dl><dt>Versions</dt><dd>Jellyfin 10.11 and 12</dd><dt>Plugin</dt><dd>Prerolls Max Intros {esc(s.plugin)}</dd><dt>Intros play before</dt><dd>Movies and episodes</dd><dt>Picked</dt><dd>For each play</dd></dl>'
             f'<a class="btn" href="{s.dl("jf12")}">Jellyfin 12 plugin</a><a class="btn ghost" href="{s.dl("jf1011")}">Jellyfin 10.11 plugin</a>'
             f'<p class="meta"><a href="{s.u("/download/#jellyfin")}">Plugin repository address</a></p>')
    s.inner_page("/jellyfin/", "Jellyfin intros plugin: prerolls with Prerolls Max",
                 "Add intro videos to Jellyfin 10.11 or 12 with the Prerolls Max Intros plugin. Plugin repository link, setup steps and which apps play intros.",
                 "Intro videos on Jellyfin", "Add the plugin repository, install one plugin, and Jellyfin picks the right intro for every movie and episode.", body,
                 [("Jellyfin", "/jellyfin/")], schema=[s.faq_ld(faq)], aside=aside)


def build_emby(s: Site):
    faq = [
        ("Do I need Emby Premiere for prerolls?", "<p>Yes. Emby plays intros through its Cinema Intros feature, and that needs Emby Premiere.</p>"),
        ("Which Emby versions work?", "<p>Emby 4.9 and later.</p>"),
        ("Why isn't a new intro playing straight away?", "<p>A brand-new intro can take up to a minute to start playing on Emby, because Emby has to register it first. Until then the movie plays without that intro.</p>"),
        ("Why do some Emby apps skip intros?", f'<p>Each Emby app has its own Cinema Intros switch under Settings, Playback, and the Roku app has it off to begin with. Samsung TV apps often don\'t play intros at all. <a href="{s.u("/docs/devices/")}">Which apps play intros</a>.</p>'),
    ]
    c = server_steps_common(s)
    steps_html = s.steps([
 ("Make an API key in Emby", '<p>Sign in as an administrator, open Settings, then API Keys, press <span class="ui">New API Key</span>, call it Prerolls Max, and copy the key.</p>'),
 ("Connect Prerolls Max to Emby", '<p>In Prerolls Max, open Media Servers and press <span class="ui">Connect Emby</span>. Enter the address you use to open Emby, like <code>http://192.168.1.10:8096</code>, and paste the key. If Prerolls Max runs in Docker, use the computer\'s network address, not <code>localhost</code>.</p>'),
 ("Install the plugin", f'<p><a href="{s.dl("emby")}">Download the Emby plugin</a> from the release, or let Prerolls Max download it for you. Unzip it and copy <code>PrerollsMax.Emby.dll</code> straight into Emby\'s plugins folder, not into a folder of its own: <code>/config/plugins</code> in Docker, <code>/var/lib/emby/plugins</code> on Linux, <code>%APPDATA%\\Emby-Server\\programdata\\plugins</code> on Windows. Restart Emby.</p>'),
 ("Let Prerolls Max set up the plugin", '<p>Press <span class="ui">Set up the plugin for me</span> on the Emby card. If Emby runs in Docker or on another computer, first change the address to this computer\'s network address with numbers, like <code>192.168.1.10</code>, because Emby\'s Docker image can\'t use <code>host.docker.internal</code>. Then play any movie and press <span class="ui">Check now</span>.</p>'),
 ("Turn on Cinema Intros", '<p>Emby only plays intros when three things are true: you have Emby Premiere, Cinema Intros is on in the server settings (turn on intros for episodes too if you want them before TV shows), and Cinema Intros is on in <strong>each</strong> Emby app under Settings, then Playback.</p>'),
 ("Test it", c["test"]),
])
    body = f"""<div class="prose">
<p>Emby plays intros through Cinema Intros, a feature of Emby Premiere. The Prerolls Max Intros plugin tells Emby which intro to play each time something starts, so you can use schedules and rules instead of one fixed list.</p>
<div class="callout"><h3>What you need</h3><p>Emby 4.9 or later with Emby Premiere, Prerolls Max running, and an administrator account on Emby.</p></div>
<h2 id="setup">Set it up</h2></div>
{steps_html}
<div class="prose">
<h2 id="apps">Which Emby apps play intros</h2>
<div class="table-wrap"><table><thead><tr><th scope="col">App</th><th scope="col">Plays intros?</th></tr></thead><tbody>
<tr><td>Web browser, phone and tablet apps</td><td>Yes, with Cinema Intros on in the app</td></tr>
<tr><td>Android TV, Fire TV</td><td>Movies only</td></tr>
<tr><td>Roku</td><td>Turn on Cinema Intros in the app. It can be unreliable.</td></tr>
<tr><td>Samsung TV</td><td>Often not. Some show "No compatible streams"; an H.264 MP4 intro sometimes helps.</td></tr>
<tr><td>Infuse</td><td>No</td></tr>
</tbody></table></div>
<p>Intros never play when you resume a movie.</p>
<h2 id="help">More help</h2>
<ul>
<li><a href="{s.u('/docs/connect-emby/')}">Connecting Emby</a>, in full</li>
<li><a href="{s.u('/docs/rules/')}">Rules: different intros for different titles</a></li>
<li><a href="{s.u('/docs/intro-not-playing/')}">My intro isn't playing</a></li>
<li>Moving from NeXroll? Remove its NeXroll Intros plugin once Prerolls Max shows Working. <a href="{s.u('/docs/moving-from-nexroll/')}">Guide</a></li>
</ul>
<h2 id="faq">Emby questions</h2></div>
{s.faq_block(faq)}"""
    aside = (f'<h2>At a glance</h2><dl><dt>Versions</dt><dd>Emby 4.9 and later</dd><dt>Needs</dt><dd>Emby Premiere</dd><dt>Plugin</dt><dd>Prerolls Max Intros {esc(s.plugin)}</dd><dt>Intros play before</dt><dd>Movies and episodes</dd></dl>'
             f'<a class="btn" href="{s.dl("emby")}">Emby plugin (.zip)</a>')
    s.inner_page("/emby/", "Emby Cinema Intros: prerolls with Prerolls Max",
                 "Set up Cinema Intros on Emby 4.9 and later with the Prerolls Max plugin. Plugin download, setup steps, Emby Premiere requirement and which apps play intros.",
                 "Intro videos on Emby", "One plugin file, Emby Premiere, and Prerolls Max chooses the intro for every play.", body,
                 [("Emby", "/emby/")], schema=[s.faq_ld(faq)], aside=aside)


def build_faq(s: Site):
    items = faq_items(s)
    s.inner_page("/faq/", "Prerolls Max FAQ: Plex, Jellyfin, Emby intro questions",
                 "Answers about Prerolls Max: cost, which media servers work, Plex Pass and Emby Premiere, TV episodes, Roku, video formats and moving from NeXroll.",
                 "Questions people ask", "Short answers. Each one links to the full guide when there is one.", s.faq_block(items),
                 [("FAQ", "/faq/")], schema=[s.faq_ld(items)])


def build_changelog(s: Site):
    def resolve(label, href):
        return s.md_link(label, href)
    md = Markdown(resolve, anchors=True)
    text = re.sub(r"^#\s+.+\n+", "", s.changelog, count=1)
    body = f'<div class="prose">{md.render(text)}</div>'
    s.inner_page("/changelog/", f"What's new in Prerolls Max {s.version}",
                 f"Release notes for Prerolls Max {s.version}: what's new compared with NeXroll 2.4.0, what's better, and what changed.",
                 "What's new", f'Release notes, newest first. Each release also has its own page on <a href="{s.gh}/releases">GitHub</a>.',
                 body, [("What's new", "/changelog/")])


def doc_nav(s: Site, current):
    groups = {}
    for d in s.docs:
        groups.setdefault(d["group"], []).append(d)
    out = ['<details class="docnav" open><summary class="docnav-toggle">All guides</summary>']
    for g in GROUP_ORDER:
        if g not in groups:
            continue
        out.append(f"<h2>{esc(g)}</h2><ul>")
        for d in groups[g]:
            cur = ' aria-current="page"' if d["path"] == current else ""
            out.append(f'<li><a href="{s.u(d["path"])}"{cur}>{esc(d["title"])}</a></li>')
        out.append("</ul>")
    out.append("</details>")
    return "".join(out)


def build_docs(s: Site):
    # Index
    groups = {}
    for d in s.docs:
        groups.setdefault(d["group"], []).append(d)
    parts = []
    for g in GROUP_ORDER:
        if g not in groups:
            continue
        dl = "".join(f'<dt><a href="{s.u(d["path"])}">{esc(d["title"])}</a></dt><dd>{esc(d["summary"])}</dd>' for d in groups[g])
        parts.append(f'<div class="group"><h2>{esc(g)}</h2><dl>{dl}</dl></div>')
    quick = f"""<p>New here? Start with <a href="{s.u('/docs/getting-started/')}">Getting started</a>, then the page for your server: <a href="{s.u('/plex/')}">Plex</a>, <a href="{s.u('/jellyfin/')}">Jellyfin</a> or <a href="{s.u('/emby/')}">Emby</a>. If an intro won't play, go to <a href="{s.u('/docs/intro-not-playing/')}">My intro isn't playing</a>. Quick answers are in the <a href="{s.u('/faq/')}">FAQ</a>.</p>"""
    s.inner_page("/docs/", "Prerolls Max documentation: guides for Plex, Jellyfin and Emby",
                 "Step-by-step Prerolls Max guides: getting started, schedules, rules, community intros, connecting Plex, Jellyfin and Emby, and fixing intros that don't play.",
                 "Documentation", "The same guides that are built into the app, plus longer deep dives.",
                 f'<div class="docs-index prose-wide">{quick}{"".join(parts)}</div>', [("Docs", "/docs/")])
    # Articles
    for d in s.docs:
        md = Markdown(s.md_link)
        body_html = md.render(d["body"])
        nav = doc_nav(s, d["path"])
        trail = [("Docs", "/docs/")] + ([("Deep dives", "/docs/")] if d["kind"] == "guide" else []) + [(d["title"], d["path"])]
        # collapse duplicate crumb target for guides
        trail = [("Docs", "/docs/"), (d["title"], d["path"])]
        edit = f'{s.gh}/blob/main/' + (f'frontend/src/help/{d["slug"]}.md' if d["kind"] == "help" else f'docs/features/{d["slug"]}.md')
        article = {"@context": "https://schema.org", "@type": "TechArticle", "headline": d["title"], "description": d["summary"],
                   "url": s.abs(d["path"]), "inLanguage": "en-GB", "isPartOf": {"@type": "WebSite", "name": "Prerolls Max", "url": s.abs("/")},
                   **({"dateModified": s.date} if s.date else {})}
        body = f'<div class="docs">{nav}<article class="prose">{body_html}<p class="doc-foot">This page is generated from <a href="{edit}" rel="noopener">{edit.split("/main/")[1]}</a> in the repository. <a href="{s.u("/docs/")}">All guides</a>.</p></article></div>'
        help_titles = {x["title"] for x in s.docs if x["kind"] == "help"}
        name = d["title"] + (" (deep dive)" if d["kind"] == "guide" and d["title"] in help_titles else "")
        page_title = f"{name} | Prerolls Max" if len(name) + 15 <= 70 else name
        desc = d["summary"] or d["title"]
        if len(desc) < 70:
            desc = f"{desc} Part of the Prerolls Max documentation for Plex, Jellyfin and Emby."
        s.inner_page(d["path"], page_title, desc[:160], d["title"], esc(d["summary"]) if d["summary"] else "", body, trail, schema=[article])


def build_404(s: Site):
    text = s.head("Page not found | Prerolls Max", "That page is not on the Prerolls Max website. Use the links on this page to find what you need.", "/404.html", noindex=True) + s.header("/404.html")
    text += f'<main id="main"><div class="page-head"><div class="wrap"><h1>That page isn\'t here</h1><p>It may have moved. Try the links below.</p></div></div><div class="wrap page"><div class="prose"><ul><li><a href="{s.u("/")}">Home</a></li><li><a href="{s.u("/download/")}">Download</a></li><li><a href="{s.u("/docs/")}">Documentation</a></li><li><a href="{s.u("/faq/")}">FAQ</a></li></ul></div></div></main>' + s.footer()
    s.add("/404.html", text)


def write_all(s: Site, out: pathlib.Path):
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for path, text in s.pages_out.items():
        target = out / "404.html" if path == "/404.html" else out / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_lf(target, text)
        if path != "/404.html":
            paths.append(path)
    assets = out / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(SITE_SRC / "assets", assets)
    shutil.copy(SITE_SRC / "site.css", assets / "site.css")
    shutil.copy(SITE_SRC / "site.js", assets / "site.js")
    lastmod = f"<lastmod>{s.date}</lastmod>" if s.date else ""
    urls = "".join(f"<url><loc>{s.abs(p)}</loc>{lastmod}</url>\n" for p in sorted(paths))
    write_lf(out / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n')
    write_lf(out / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {s.origin}/sitemap.xml\n")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def build(repository: str, out: pathlib.Path) -> Site:
    s = Site(repository)
    build_home(s)
    build_download(s)
    build_plex(s)
    build_jellyfin(s)
    build_emby(s)
    build_faq(s)
    build_changelog(s)
    build_docs(s)
    build_404(s)
    write_all(s, out)
    return s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$", args.repository):
        sys.exit(f"Not a GitHub owner/repo: {args.repository!r}")
    s = build(args.repository, args.out)
    for w in sorted(set(s.warnings)):
        print("warning:", w, file=sys.stderr)
    print(f"Built {len(s.pages_out)} pages for {args.repository} into {args.out}")


if __name__ == "__main__":
    main()
