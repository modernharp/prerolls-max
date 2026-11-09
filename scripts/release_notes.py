#!/usr/bin/env python3
"""Release notes for a version: its CHANGELOG section plus how to install.

    python scripts/release_notes.py 1.0.0 --repository owner/repo > notes.md

The CHANGELOG section is ``## [<version>]`` up to the next ``## [``. The
install part names this repository's image, Jellyfin catalog and installer, so
the notes are right for whichever GitHub account publishes the release.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "app" / "CHANGELOG.md"


def changelog_section(version: str, text: str) -> str:
    pattern = re.compile(r"^## \[" + re.escape(version) + r"\][^\n]*\n(.*?)(?=^## \[|\Z)", re.S | re.M)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def notes(version: str, repository: str) -> str:
    owner, _, repo = repository.partition("/")
    image = f"ghcr.io/{owner.lower()}/prerolls-max"
    pages = f"https://{owner.lower()}.github.io/{repo}"
    section = changelog_section(version, CHANGELOG.read_text(encoding="utf-8"))
    if not section:
        section = f"No changelog entry for {version} yet; see the commits since the last release."
    return f"""## Prerolls Max {version}

**Prerolls Max replaces NeXroll.** It is a continuation of NeXroll 2.4.0 (MIT) with a new interface. You can:

- **Replace NeXroll (recommended):** the Windows installer stops NeXroll and switches it off. NeXroll is not uninstalled and its files stay. Import your NeXroll library in **Settings > Moving from NeXroll**. With Docker, stop the NeXroll container and give Prerolls Max NeXroll's `/data` folder (it copies `nexroll.db`; NeXroll's file isn't changed).
- **Keep NeXroll running too (advanced):** choose it in the installer (or run `PrerollsMax_Installer_v{version}.exe /S /KEEPNEXROLL /PORT=9494`), or run the container on another host port (`-p 9494:9393`). Let only one of them manage intros on each media server.

### Install

- **Docker:** `docker run -d --name prerollsmax -p 9393:9393 -v prerollsmax-data:/data -v /path/to/prerolls:/data/prerolls {image}:{version}` (or `:latest` for the newest stable release). Images for amd64 and arm64.
- **Windows:** download `PrerollsMax_Installer_v{version}.exe` below and run it. Silent: `/S`.
- **Jellyfin plugin:** in Jellyfin, Dashboard > Plugins > Repositories, add `{pages}/jellyfin/manifest.json` (Jellyfin 12) or `{pages}/jellyfin/manifest-10.11.json` (Jellyfin 10.11). Or download the zip below.
- **Emby plugin:** download `PrerollsMax.Emby-*.zip`, put `PrerollsMax.Emby.dll` in Emby's `plugins` folder and restart Emby.
- **Unraid:** `prerolls-max.xml` below is a ready template.

Check downloads against `SHA256SUMS.txt`.

### Changes

{section}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    if "/" not in args.repository:
        sys.exit("--repository must be owner/repo")
    sys.stdout.write(notes(args.version.lstrip("vV"), args.repository))


if __name__ == "__main__":
    main()
