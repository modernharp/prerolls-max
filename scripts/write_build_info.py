#!/usr/bin/env python3
"""Write build_info.json: which GitHub repository built this copy.

The app reads it (app/backend/build_info.py) to know where update checks look
and which project link to show; the Windows updater script reads the copy in
the install folder. Nothing in the source names a GitHub account: the release
workflows run this with GitHub's own variables, so a fork or a move to another
account needs no edits.

    python scripts/write_build_info.py --out app/backend/build_info.json

Values, each from an option or else the environment:
    --repository  PMAX_BUILD_REPOSITORY if set, else GITHUB_REPOSITORY: owner/repo
                  ("" or "none": no update source, update checks stay off)
    --commit      GITHUB_SHA
    --image       PMAX_IMAGE         default ghcr.io/<owner, lower case>/prerolls-max
    --version     else read from --version-file (default app/version.py)
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$")


def app_version(path: pathlib.Path = ROOT / "app" / "version.py") -> str:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(r"""__version__\s*=\s*['"]([^'"]+)['"]""", text)
    if not match:
        sys.exit("app/version.py has no __version__")
    return match.group(1)


def build_info(repository: str, commit: str, image: str, version: str) -> dict:
    repository = (repository or "").strip()
    if repository.lower() in ("none", "off", "-"):
        repository = ""
    if repository and not REPOSITORY_RE.match(repository):
        sys.exit(f"Not a GitHub owner/repo: {repository!r}")
    if not image and repository:
        image = f"ghcr.io/{repository.split('/')[0].lower()}/prerolls-max"
    return {
        "repository": repository,
        "version": version,
        "commit": (commit or "").strip(),
        "image": image or "",
        "built_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=pathlib.Path, action="append",
                        help="file to write (repeat to write several copies)")
    parser.add_argument("--repository", default=os.environ.get(
        "PMAX_BUILD_REPOSITORY", os.environ.get("GITHUB_REPOSITORY", "")))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--image", default=os.environ.get("PMAX_IMAGE", ""))
    parser.add_argument("--version", default="")
    parser.add_argument("--version-file", type=pathlib.Path, default=ROOT / "app" / "version.py")
    args = parser.parse_args()
    info = build_info(args.repository, args.commit, args.image, args.version or app_version(args.version_file))
    text = json.dumps(info, indent=2) + "\n"
    for out in args.out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}: repository={info['repository'] or '(none: update checks off)'} version={info['version']}")


if __name__ == "__main__":
    main()
