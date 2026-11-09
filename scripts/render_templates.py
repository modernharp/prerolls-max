#!/usr/bin/env python3
"""Fill in the repository-specific templates for a release.

    python scripts/render_templates.py --repository owner/repo --out site

Writes:
    <out>/unraid/prerolls-max.xml   the Unraid template (from unraid/prerolls-max.xml)
    <out>/ (the whole website)      built by scripts/build_site.py: home, Plex, Jellyfin, Emby,
                                    download, FAQ, changelog and docs pages, sitemap.xml, robots.txt
    <out>/.nojekyll                 serve files as they are

The release workflow runs it on the gh-pages checkout. Nothing in the source
names a GitHub account; the values come from GITHUB_REPOSITORY.
"""
import argparse
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_site  # noqa: E402

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
    site = build_site.build(args.repository, args.out)
    for warning in sorted(set(site.warnings)):
        print("warning:", warning, file=sys.stderr)
    (args.out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Rendered templates for {args.repository} into {args.out}")


if __name__ == "__main__":
    main()
