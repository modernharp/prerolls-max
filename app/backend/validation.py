"""Reusable input checks with messages a non-technical person can act on.

Use them as pydantic field types::

    class PlexConnect(BaseModel):
        url: ServerUrl
        token: Token

or call the ``clean_*`` functions directly from endpoints that take form
data. Every ``clean_*`` function returns the cleaned value or raises
``ValueError`` with a finished sentence; pydantic turns that into a field
error and errors.py shows it next to the field.
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
import ntpath
import os
import posixpath
import re
import unicodedata
from typing import Annotated, Optional
from urllib.parse import urlsplit, urlunsplit

from pydantic import AfterValidator, BeforeValidator

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

def clean_server_url(value: str, *, service: str = "the server", default_port: Optional[int] = None) -> str:
    """A Plex/Jellyfin/Emby/Radarr/Sonarr address: http(s)://host[:port][/path].

    Adds http:// when the scheme is missing (people type "192.168.1.5:32400"),
    removes a trailing slash, and rejects anything that isn't a web address.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Enter the address of {service}.")
    text = value.strip()
    if any(c.isspace() for c in text):
        raise ValueError("The address can't contain spaces.")
    if len(text) > 2048:
        raise ValueError("That address is too long.")
    if "://" not in text:
        # "plex:32400" is a host and port; "javascript:..." or "file:..." is a scheme.
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)", text):
            raise ValueError("The address must start with http:// or https://.")
        text = "http://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("The address must start with http:// or https://.")
    if not parts.hostname:
        raise ValueError("Add the computer name or IP address, like http://192.168.1.10:32400.")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("The port number must be between 1 and 65535.")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("The port number must be between 1 and 65535.")
    if parts.username or parts.password:
        raise ValueError("Leave the user name and password out of the address.")
    if parts.query or parts.fragment:
        raise ValueError("Remove everything after ? or # from the address.")
    netloc = parts.netloc
    if port is None and default_port:
        netloc = f"{netloc}:{default_port}"
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))


def is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in ("localhost",) or host.endswith(".local") or host.endswith(".lan")
    return ip.is_private or ip.is_loopback or ip.is_link_local


# ---------------------------------------------------------------------------
# Tokens and keys
# ---------------------------------------------------------------------------

def clean_token(value: str, *, what: str = "token", min_len: int = 8, max_len: int = 512) -> str:
    """API keys and tokens: trims, rejects inner spaces and pasted quotes."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Paste the {what}.")
    text = value.strip().strip('"').strip("'").strip()
    if any(c.isspace() for c in text):
        raise ValueError(f"The {what} can't contain spaces. Copy it again without extra text.")
    if _CONTROL.search(text):
        raise ValueError(f"The {what} contains characters that can't be part of a {what}.")
    if len(text) < min_len:
        raise ValueError(f"That {what} looks too short. Copy the whole thing.")
    if len(text) > max_len:
        raise ValueError(f"That {what} looks too long. Copy only the {what}.")
    return text


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def clean_name(value: str, *, what: str = "name", max_len: int = 100) -> str:
    """Names people type: collections, schedules, sequences, servers."""
    if not isinstance(value, str):
        raise ValueError(f"Enter a {what}.")
    text = unicodedata.normalize("NFC", " ".join(value.split()))
    if not text:
        raise ValueError(f"Enter a {what}.")
    if _CONTROL.search(text):
        raise ValueError(f"The {what} contains characters that can't be used.")
    if len(text) > max_len:
        raise ValueError(f"Keep the {what} to {max_len} characters or fewer.")
    return text


_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}


def clean_filename(value: str, *, max_len: int = 150) -> str:
    """A file name (no folders) that works on Windows, Linux and in Plex's list.

    Plex separates prerolls with "," and ";", so file names can't contain them.
    """
    text = clean_name(value, what="file name", max_len=max_len)
    bad = sorted(set(re.findall(r'[\\/:*?"<>|,;]', text)))
    if bad:
        raise ValueError("File names can't contain " + " ".join(bad) + ".")
    if text in (".", "..") or text.endswith(".") or text.endswith(" "):
        raise ValueError("File names can't end with a dot or a space.")
    if text.split(".")[0].upper() in _WIN_RESERVED:
        raise ValueError(f"\"{text}\" is a reserved name on Windows. Pick another.")
    return text


def plex_safe_filename(value: str) -> str:
    """Replace the characters Plex can't take in a preroll list with dashes."""
    return re.sub(r"\s*[,;]\s*", " - ", value).strip()


# ---------------------------------------------------------------------------
# Folders and files on disk
# ---------------------------------------------------------------------------

def clean_folder_path(value: str, *, what: str = "folder") -> str:
    """An absolute folder path in Windows or Linux/macOS form."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Enter the {what}.")
    text = value.strip().strip('"').strip("'")
    if "\x00" in text or _CONTROL.search(text):
        raise ValueError(f"The {what} contains characters that can't be part of a path.")
    if len(text) > 4096:
        raise ValueError(f"That {what} path is too long.")
    if text.startswith(("http://", "https://", "smb://", "nfs://")):
        raise ValueError(f"Enter a folder path, not a web or network address. Map the share as a folder first.")
    windows = bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith("\\\\")
    if windows:
        norm = ntpath.normpath(text)
    elif text.startswith("/"):
        norm = posixpath.normpath(text)
        if norm.startswith("//"):
            norm = "/" + norm.lstrip("/")
    else:
        raise ValueError(
            "Use the full path from the top, like /data/prerolls on Linux or Docker, "
            "or D:\\Prerolls on Windows."
        )
    if ".." in re.split(r"[\\/]", text):
        raise ValueError(f"The {what} path can't contain \"..\". Use the full path.")
    return norm


def path_style(path: str) -> str:
    """"windows" or "posix"."""
    return "windows" if re.match(r"^[A-Za-z]:[\\/]", path or "") or (path or "").startswith("\\\\") else "posix"


# ---------------------------------------------------------------------------
# Times and dates
# ---------------------------------------------------------------------------

def clean_time_hhmm(value: str) -> str:
    """"7:5" -> "07:05". Accepts 24-hour time with an optional am/pm."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a time like 18:30.")
    text = value.strip().lower().replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?", text)
    if not m:
        raise ValueError("Enter a time like 18:30 or 6:30 pm.")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if not 1 <= hour <= 12:
            raise ValueError("With am or pm, the hour must be between 1 and 12.")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("That time doesn't exist. Use hours 0-23 and minutes 0-59.")
    return f"{hour:02d}:{minute:02d}"


def parse_date(value) -> _dt.date:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a date like 2026-12-24.")
    text = value.strip()[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        raise ValueError("Enter a date like 2026-12-24.")


def parse_datetime(value) -> _dt.datetime:
    """ISO date-times from browsers, with or without seconds or a time zone.

    A time zone suffix is dropped: schedules are in Prerolls Max's own time zone.
    """
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a date and time like 2026-12-24 18:30.")
    text = value.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1]
    text = re.sub(r"[+-]\d{2}:?\d{2}$", "", text)
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            return _dt.datetime.combine(_dt.date.fromisoformat(text[:10]), _dt.time())
        except ValueError:
            raise ValueError("Enter a date and time like 2026-12-24 18:30.")


def check_date_range(start, end, *, start_label: str = "start", end_label: str = "end") -> None:
    if start is not None and end is not None and end < start:
        raise ValueError(f"The {end_label} must be after the {start_label}.")


def clean_hex_color(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#?[0-9a-fA-F]{6}", value.strip()):
        raise ValueError("Pick a colour, or enter one like #3366FF.")
    text = value.strip()
    return ("#" + text.lstrip("#")).upper()


# ---------------------------------------------------------------------------
# Pydantic field types
# ---------------------------------------------------------------------------

ServerUrl = Annotated[str, AfterValidator(clean_server_url)]
Token = Annotated[str, AfterValidator(clean_token)]
ApiKey = Annotated[str, AfterValidator(lambda v: clean_token(v, what="API key", min_len=16))]
Name = Annotated[str, AfterValidator(clean_name)]
FileName = Annotated[str, AfterValidator(clean_filename)]
FolderPath = Annotated[str, AfterValidator(clean_folder_path)]
TimeHHMM = Annotated[str, AfterValidator(clean_time_hhmm)]
DateValue = Annotated[_dt.date, BeforeValidator(parse_date)]
DateTimeValue = Annotated[_dt.datetime, BeforeValidator(parse_datetime)]
HexColor = Annotated[str, AfterValidator(clean_hex_color)]
Stripped = Annotated[str, BeforeValidator(_strip)]
