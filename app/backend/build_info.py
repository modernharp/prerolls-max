"""What this copy of Prerolls Max was built from.

Release builds (the GitHub Actions workflows, the Dockerfile and the Windows
build) write a small ``build_info.json`` with ``scripts/write_build_info.py``:

    {"repository": "owner/repo", "version": "1.0.0", "commit": "abc123",
     "built_at": "2026-01-01T00:00:00Z", "image": "ghcr.io/owner/prerolls-max"}

``repository`` is the GitHub repository that built and publishes this copy,
taken from ``GITHUB_REPOSITORY`` at build time. It decides where the update
check looks and which project link the app and the tray show. Nothing here is
hard-coded to one GitHub account, so the project can move to any repository.

A copy run from source has no file, so update checks stay off and the app says
so (see ``brand.release_api_url``). ``PMAX_UPDATE_REPO`` overrides the file.

Where the file is looked for, first match wins:
  1. ``PMAX_BUILD_INFO`` (a path)
  2. next to this module (``backend/build_info.json``)
  3. the folder above it (``/app/server`` in Docker, ``app/`` in a checkout)
  4. PyInstaller's bundle folder, then the folder holding the .exe
"""

import json
import os
import re
import sys

FILENAME = "build_info.json"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$")

_cache = None


def _candidates():
    explicit = (os.environ.get("PMAX_BUILD_INFO") or "").strip()
    if explicit:
        yield explicit
    here = os.path.dirname(os.path.abspath(__file__))
    yield os.path.join(here, FILENAME)
    yield os.path.join(os.path.dirname(here), FILENAME)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        yield os.path.join(bundle, FILENAME)
    if getattr(sys, "frozen", False):
        yield os.path.join(os.path.dirname(os.path.abspath(sys.executable)), FILENAME)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load(refresh=False):
    """The build info as a dict ({} when this copy has none)."""
    global _cache
    if _cache is None or refresh:
        _cache = {}
        for path in _candidates():
            data = _read(path)
            if data is not None:
                _cache = data
                break
    return _cache


def valid_repository(value):
    """``owner/repo`` when ``value`` looks like one, else ''."""
    value = str(value or "").strip().strip("/")
    if value.lower().startswith("https://github.com/"):
        value = value[len("https://github.com/"):].strip("/")
    return value if REPOSITORY_RE.match(value) and ".." not in value else ""


def repository():
    """The GitHub ``owner/repo`` this copy was built from, or ''."""
    return valid_repository(load().get("repository"))
