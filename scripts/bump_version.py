#!/usr/bin/env python3
"""Show, check or change the Prerolls Max version everywhere it is written.

    python scripts/bump_version.py                 print the versions
    python scripts/bump_version.py --check         fail if any file disagrees (CI runs this)
    python scripts/bump_version.py --check --tag v1.2.3   ...and the tag must match (release runs this)
    python scripts/bump_version.py 1.2.3           set the app version
    python scripts/bump_version.py 1.2.3 --plugin 2.2.0.0   also set the plugin version

The app version (``app/version.py``) is the one source. These copies follow it:
    app/backend/version.py      fallback literal for frozen builds
    frontend/package.json       "version"
    frontend/package-lock.json  "version" (twice)

Built from it at build time, so never edited by hand:
    the Windows .exe version resource (packaging/windows/make_version_info.py)
    the installer name and version (packaging/windows/build.ps1 passes it to NSIS)
    the Docker image tags (.github/workflows/docker.yml)

The Jellyfin/Emby plugin has its own four-part version
(``plugins/Directory.Build.props``, PrerollsMaxPluginVersion), because Jellyfin
needs a.b.c.d and orders updates by it. Bump it with ``--plugin`` whenever
plugin code changes; it must only ever go up.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?$")
PLUGIN_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
PY_RE = re.compile(r"""^__version__\s*=\s*['"]([^'"]+)['"]""", re.MULTILINE)
PLUGIN_PROP_RE = re.compile(r"<PrerollsMaxPluginVersion>([^<]+)</PrerollsMaxPluginVersion>")

APP_PY = ROOT / "app" / "version.py"
BACKEND_PY = ROOT / "app" / "backend" / "version.py"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
PACKAGE_LOCK = ROOT / "frontend" / "package-lock.json"
PLUGIN_PROPS = ROOT / "plugins" / "Directory.Build.props"


def read_py(path):
    match = PY_RE.search(path.read_text(encoding="utf-8-sig"))
    return match.group(1) if match else None


def current():
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    plugin = PLUGIN_PROP_RE.search(PLUGIN_PROPS.read_text(encoding="utf-8"))
    return {
        "app/version.py": read_py(APP_PY),
        "app/backend/version.py": read_py(BACKEND_PY),
        "frontend/package.json": json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get("version"),
        "frontend/package-lock.json": lock.get("version"),
        'frontend/package-lock.json packages[""]': lock.get("packages", {}).get("", {}).get("version"),
        "plugins/Directory.Build.props (plugin)": plugin.group(1) if plugin else None,
    }


def write_py(path, version):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text, n = PY_RE.subn(f"__version__ = '{version}'", raw.decode("utf-8-sig"), count=1)
    if n != 1:
        sys.exit(f"No __version__ line in {path}")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def write_json_version(path, version, count):
    # Regex, not json.dump, so formatting and key order stay as they are.
    text, n = re.subn(r'^(\s*)"version":\s*"[^"]*"', rf'\g<1>"version": "{version}"',
                      path.read_text(encoding="utf-8"), count=count, flags=re.MULTILINE)
    if n != count:
        sys.exit(f"Expected {count} version line(s) in {path}, found {n}")
    path.write_text(text, encoding="utf-8")
    json.loads(path.read_text(encoding="utf-8"))


def write_plugin(version):
    text, n = PLUGIN_PROP_RE.subn(f"<PrerollsMaxPluginVersion>{version}</PrerollsMaxPluginVersion>",
                                  PLUGIN_PROPS.read_text(encoding="utf-8"), count=1)
    if n != 1:
        sys.exit(f"No PrerollsMaxPluginVersion in {PLUGIN_PROPS}")
    PLUGIN_PROPS.write_text(text, encoding="utf-8")


def check(tag=None):
    values = current()
    app = values["app/version.py"]
    problems = []
    if not app or not VERSION_RE.match(app):
        problems.append(f"app/version.py has {app!r}; expected X.Y.Z or X.Y.Z-alpha.N / -beta.N / -rc.N")
    for name, value in values.items():
        if name.startswith("plugins/"):
            if not value or not PLUGIN_RE.match(value):
                problems.append(f"{name} has {value!r}; expected four numbers a.b.c.d")
        elif value != app:
            problems.append(f"{name} has {value!r}, app/version.py has {app!r}")
    if tag is not None and tag.lstrip("vV") != app:
        problems.append(f"tag {tag!r} does not match app/version.py ({app!r}); tag v{app} or bump first")
    for p in problems:
        print(f"ERROR: {p}", file=sys.stderr)
    if problems:
        print("Fix with: python scripts/bump_version.py <version>", file=sys.stderr)
        sys.exit(1)
    print(f"OK: app {app}, plugin {values['plugins/Directory.Build.props (plugin)']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--plugin", help="also set the plugin version (a.b.c.d)")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--tag", help="with --check: the release tag that must match")
    args = parser.parse_args()

    if args.check:
        check(args.tag)
        return
    if not args.version and not args.plugin:
        for name, value in current().items():
            print(f"{name}: {value}")
        return
    if args.version:
        version = args.version.lstrip("vV")
        if not VERSION_RE.match(version):
            sys.exit(f"{version!r} isn't a version like 1.2.3 or 1.2.3-beta.1")
        write_py(APP_PY, version)
        write_py(BACKEND_PY, version)
        write_json_version(PACKAGE_JSON, version, 1)
        write_json_version(PACKAGE_LOCK, version, 2)
        print(f"App version is now {version}.")
    if args.plugin:
        if not PLUGIN_RE.match(args.plugin):
            sys.exit(f"{args.plugin!r} isn't a plugin version like 2.2.0.0")
        old = current()["plugins/Directory.Build.props (plugin)"]
        if old and PLUGIN_RE.match(old) and tuple(map(int, args.plugin.split("."))) <= tuple(map(int, old.split("."))):
            sys.exit(f"The plugin version must go up (it is {old}).")
        write_plugin(args.plugin)
        print(f"Plugin version is now {args.plugin}.")
    check()
    print("Next: add a CHANGELOG entry (app/CHANGELOG.md), commit, then tag v<version> to release.")


if __name__ == "__main__":
    main()
