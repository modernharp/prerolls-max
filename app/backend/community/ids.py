"""Community item ids carry their library: ``pm:<slug>`` or ``tn:<path>``.

* ``pm:`` Prerolls.me, followed by the item's slug (``pm:x-logo-emby-pre-roll``).
* ``tn:`` Prerolls.uk (Typical Nerds), followed by the file's path on the
  server (``tn:/Holidays/Christmas/Snow%20-%20Plex.mp4``).

Installs from before Prerolls Max stored the bare path. :func:`tag_legacy`
turns one of those into the tagged form and leaves tagged ids and ids it
can't read (the old "mangled" ``_Holidays_...`` form) alone, so it is safe to
apply to anything, any number of times.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from backend.errors import bad_input

PREFIXES = {"pm": "prerollsme", "tn": "prerollsuk"}
PREFIX_OF = {v: k for k, v in PREFIXES.items()}

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_PATH = 1024


def tag_legacy(value) -> Optional[str]:
    """``/a/b.mp4`` -> ``tn:/a/b.mp4``; tagged and unreadable ids unchanged."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(("pm:", "tn:")):
        return text
    if text.startswith("/") and not text.startswith("//"):
        return "tn:" + text
    return text


def is_tagged(value) -> bool:
    return isinstance(value, str) and value.startswith(("pm:", "tn:"))


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and bool(_SLUG.fullmatch(slug))


def make(source_id: str, key: str) -> str:
    return f"{PREFIX_OF[source_id]}:{key}"


def valid_path(path: str) -> bool:
    """A Prerolls.uk file path: absolute, no host, no way out of the server root."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return False
    if len(path) > MAX_PATH or "\\" in path or "?" in path or "#" in path or _CONTROL.search(path):
        return False
    from urllib.parse import unquote
    segments = unquote(path).split("/")
    return ".." not in segments and "." not in segments


def split(item_id, *, field: str = "id") -> Tuple[str, str]:
    """(source id, key) for a tagged id, or a bare legacy path. Raises a 422
    with a plain message for anything else."""
    tagged = tag_legacy(item_id)
    if not tagged or ":" not in tagged[:3]:
        raise bad_input("That doesn't look like a community intro video.", field=field,
                        hint="Pick the video again from the Community page.")
    prefix, key = tagged.split(":", 1)
    source = PREFIXES.get(prefix)
    if source == "prerollsme" and _SLUG.fullmatch(key):
        return source, key
    if source == "prerollsuk" and valid_path(key):
        return source, key
    raise bad_input("That doesn't look like a community intro video.", field=field,
                    hint="Pick the video again from the Community page.")
