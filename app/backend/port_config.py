"""Which port Prerolls Max listens on, and a plain message when it's taken.

The port comes from, in order:

1. ``PMAX_PORT`` (or ``NEXROLL_PORT``, see brand.py) in the environment. Docker
   sets this, and it always wins.
2. ``startup.json`` next to the database: ``{"port": 9494}``. Settings, "Moving
   from NeXroll", writes it so Prerolls Max can run beside NeXroll. The Windows
   service, the tray app and ``python -m backend.main`` read it at start.
3. 9393, the same default as NeXroll.

Only the standard library is used here: the Windows service and tray app copy
the small ``read_port`` logic without importing the backend.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from typing import Optional, Tuple

DEFAULT_PORT = 9393
NEXROLL_PORT = 9393
MIN_PORT = 1024
MAX_PORT = 65535
FILE_NAME = "startup.json"


def data_folder(environ=None) -> str:
    """The folder that holds the database (and startup.json)."""
    env = os.environ if environ is None else environ
    path = (env.get("PMAX_DB_PATH") or "").strip()
    if path:
        return os.path.dirname(os.path.abspath(path))
    folder = (env.get("PMAX_DB_DIR") or "").strip()
    if folder:
        return os.path.abspath(folder)
    try:
        from backend.database import DB_PATH  # the folder the app really uses
        return os.path.dirname(DB_PATH)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        base = env.get("ProgramData") or env.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Prerolls Max")
    return os.path.join(os.getcwd(), "data")


def config_path(environ=None) -> str:
    return os.path.join(data_folder(environ), FILE_NAME)


def _valid(port) -> Optional[int]:
    try:
        value = int(str(port).strip())
    except (TypeError, ValueError):
        return None
    return value if MIN_PORT <= value <= MAX_PORT else None


def saved_port(environ=None) -> Optional[int]:
    """The port saved in startup.json, or None."""
    try:
        with open(config_path(environ), "r", encoding="utf-8") as fh:
            return _valid((json.load(fh) or {}).get("port"))
    except (OSError, ValueError, AttributeError):
        return None


def env_port(environ=None) -> Optional[int]:
    env = os.environ if environ is None else environ
    raw = (env.get("PMAX_PORT") or env.get("NEXROLL_PORT") or "").strip()
    return _valid(raw) if raw else None


def configured_port(environ=None) -> Tuple[int, str]:
    """(port, where it came from: "environment" | "settings" | "default")."""
    port = env_port(environ)
    if port:
        return port, "environment"
    port = saved_port(environ)
    if port:
        return port, "settings"
    return DEFAULT_PORT, "default"


def save_port(port: Optional[int], environ=None) -> None:
    """Write (or with None, remove) the port for the next start."""
    path = config_path(environ)
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        data = {}
    if port is None:
        data.pop("port", None)
    else:
        data["port"] = int(port)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def port_free(port: int, host: str = "0.0.0.0") -> bool:
    """True when nothing listens on ``port`` (we could bind it right now)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not sys.platform.startswith("win"):
            # Same as uvicorn: a socket in TIME_WAIT doesn't count as taken.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def identify(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> Optional[str]:
    """Who answers on this port: "nexroll", "prerollsmax", "other", or None when nothing does."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    try:
        req = Request(f"http://{host}:{int(port)}/", headers={"Accept": "text/html"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed local address
            page = resp.read(65536).decode("utf-8", "replace")
    except HTTPError as exc:
        page = ""
        try:
            page = exc.read(65536).decode("utf-8", "replace")
        except Exception:
            pass
    except (URLError, OSError, ValueError):
        return None
    lowered = page.lower()
    if "<title>nexroll" in lowered:
        return "nexroll"
    if "prerolls max" in lowered:
        return "prerollsmax"
    return "other"


def in_use_message(port: int, who: Optional[str], source: str = "default") -> str:
    """What to print when ``port`` is taken. Plain words, no traceback."""
    if who == "prerollsmax":
        return (f"Port {port} is already in use by another copy of Prerolls Max. "
                "Only one can run at a time; stop the other one first.")
    lead = (f"Port {port} is already in use, by NeXroll." if who == "nexroll"
            else f"Port {port} is already in use, probably by NeXroll." if port == NEXROLL_PORT
            else f"Port {port} is already in use by another program.")
    how = ("Stop NeXroll, or give Prerolls Max another port: set PMAX_PORT, or pick one in "
           "Settings > Moving from NeXroll.") if port == NEXROLL_PORT or who == "nexroll" else (
        "Close that program, or give Prerolls Max another port: set PMAX_PORT, or pick one in "
        "Settings > Moving from NeXroll.")
    where = {"environment": " (The port comes from PMAX_PORT.)",
             "settings": f" (The port was picked in Settings and saved in {FILE_NAME}.)"}.get(source, "")
    return f"{lead} {how}{where}"


def check_before_start(port: int, source: str = "default", host: str = "0.0.0.0") -> Optional[str]:
    """None when the port is free, else the message to show."""
    if port_free(port, host):
        return None
    return in_use_message(port, identify(port), source)
