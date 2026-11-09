"""Product identity for Prerolls Max.

Prerolls Max is a fork of NeXroll (https://github.com/JFLXCLOUD/NeXroll, MIT).
Every user-facing product name, data file name and update source comes from
here so a rename only touches one file.
"""

import os

APP_NAME = "Prerolls Max"
APP_SLUG = "prerollsmax"          # file names, cookies, mutexes
ENV_PREFIX = "PMAX_"
LEGACY_ENV_PREFIX = "NEXROLL_"    # NeXroll settings keep working
DB_FILENAME = "prerollsmax.db"
LEGACY_DB_FILENAME = "nexroll.db"  # picked up once, copied, never changed
SESSION_COOKIE = "pmax_session"
UPSTREAM_URL = "https://github.com/JFLXCLOUD/NeXroll"

try:
    from backend import build_info as _build_info
except ImportError:  # imported as a top-level module (backend/ on sys.path)
    import build_info as _build_info

# Values that switch update checks off on purpose.
_OFF = {"off", "none", "false", "0", "-"}


def _update_repo():
    raw = (os.environ.get("PMAX_UPDATE_REPO") or "").strip()
    if raw.lower() in _OFF:
        return ""
    return _build_info.valid_repository(raw) or _build_info.repository()


# GitHub "owner/repo" that publishes Prerolls Max releases: PMAX_UPDATE_REPO,
# else the repository that built this copy (build_info.json, written by the
# release workflows from GITHUB_REPOSITORY). Empty means update checks are
# switched off and the app says so instead of failing.
UPDATE_REPO = _update_repo()

# This project's home page, or "" for a copy built outside GitHub Actions.
PROJECT_URL = f"https://github.com/{UPDATE_REPO}" if UPDATE_REPO else ""

USER_AGENT_URL = PROJECT_URL


def user_agent_comment(extra=""):
    """The "(+link; extra)" part of a User-Agent, without a link when unknown."""
    parts = [p for p in (f"+{USER_AGENT_URL}" if USER_AGENT_URL else "", extra) if p]
    return f" ({'; '.join(parts)})" if parts else ""


def apply_env_aliases(environ=None):
    """Copy NEXROLL_* settings to PMAX_* when the new name isn't set.

    People moving from NeXroll can keep their Docker or service settings.
    The PMAX_ name always wins when both are present.
    """
    env = os.environ if environ is None else environ
    for key in list(env.keys()):
        if key.startswith(LEGACY_ENV_PREFIX):
            new_key = ENV_PREFIX + key[len(LEGACY_ENV_PREFIX):]
            if not env.get(new_key):
                env[new_key] = env[key]
    return env


def release_api_url(path="releases/latest"):
    """GitHub API URL for our releases, or None when updates aren't set up."""
    if not UPDATE_REPO:
        return None
    return f"https://api.github.com/repos/{UPDATE_REPO}/{path}"
