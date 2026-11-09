#!/usr/bin/env python3
"""Fill in the repository-specific templates for a release.

    python scripts/render_templates.py --repository owner/repo --out site

Writes:
    <out>/unraid/prerolls-max.xml   the Unraid template (from unraid/prerolls-max.xml)
    <out>/index.html                the GitHub Pages front page (Jellyfin catalog links)
    <out>/.nojekyll                 serve files as they are

The release workflow runs it on the gh-pages checkout. Nothing in the source
names a GitHub account; the values come from GITHUB_REPOSITORY.
"""
import argparse
import html
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$")


def values(repository: str) -> dict:
    owner, repo = repository.split("/")
    return {
        "OWNER": owner,
        "OWNER_LOWER": owner.lower(),
        "REPO": repo,
        "IMAGE": f"ghcr.io/{owner.lower()}/prerolls-max",
    }


def render(text: str, vals: dict) -> str:
    out = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: vals[m.group(1)], text)
    if "{{" in out:
        sys.exit("A template placeholder was left unfilled")
    return out


def index_html(vals: dict) -> str:
    v = {k: html.escape(s) for k, s in vals.items()}
    pages = f"https://{v['OWNER_LOWER']}.github.io/{v['REPO']}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prerolls Max</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}}code{{background:#eee;padding:.1rem .3rem;border-radius:4px;word-break:break-all}}</style>
</head><body>
<h1>Prerolls Max</h1>
<p>Intro videos (prerolls) for Plex, Jellyfin and Emby. Prerolls Max replaces NeXroll.</p>
<h2>Jellyfin plugin repository</h2>
<p>In Jellyfin, open Dashboard, Plugins, Repositories, and add the one for your server:</p>
<ul>
<li>Jellyfin 12: <code>{pages}/jellyfin/manifest.json</code></li>
<li>Jellyfin 10.11: <code>{pages}/jellyfin/manifest-10.11.json</code></li>
</ul>
<h2>Other downloads</h2>
<ul>
<li><a href="https://github.com/{v['OWNER']}/{v['REPO']}/releases">Releases</a>: Windows installer, Emby plugin, checksums</li>
<li>Docker: <code>docker pull {v['IMAGE']}:latest</code></li>
<li>Unraid template: <code>{pages}/unraid/prerolls-max.xml</code></li>
</ul>
</body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if not REPOSITORY_RE.match(args.repository or ""):
        sys.exit(f"Not a GitHub owner/repo: {args.repository!r}")
    vals = values(args.repository)
    (args.out / "unraid").mkdir(parents=True, exist_ok=True)
    (args.out / "unraid" / "prerolls-max.xml").write_text(
        render((ROOT / "unraid" / "prerolls-max.xml").read_text(encoding="utf-8"), vals), encoding="utf-8")
    (args.out / "index.html").write_text(index_html(vals), encoding="utf-8")
    (args.out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Rendered templates for {args.repository} into {args.out}")


if __name__ == "__main__":
    main()
