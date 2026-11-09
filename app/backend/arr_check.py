"""Connection test shared by Radarr and Sonarr.

Both answer /api/v3/system/status with their name in appName, so the test can
tell "that's Sonarr, not Radarr" apart from a wrong key. Both also answer
/ping without a key, which tells "wrong key" apart from "something else is
listening on that port" (Plex, a router page, Prerolls Max itself).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

PORTS = {"Radarr": 7878, "Sonarr": 8989}
# What each app is for, so a mix-up can say where the address belongs.
SECTIONS = {
    "Radarr": "Radarr (movies)",
    "Sonarr": "Sonarr (TV shows)",
}


def _fail(message: str) -> Dict[str, Any]:
    return {"success": False, "message": message}


def _not_this_app(name: str) -> Dict[str, Any]:
    return _fail(f"Something answered at that address, but it isn't {name}. "
                 f"Check the port: {name} usually uses {PORTS.get(name, '')}.")


def _wrong_app(name: str, found: str) -> Dict[str, Any]:
    if found in SECTIONS:
        return _fail(f"That address is {found}, not {name}. Add it under {SECTIONS[found]} instead.")
    return _fail(f"That address is {found}, not {name}. "
                 f"Check the port: {name} usually uses {PORTS.get(name, '')}.")


async def _looks_like_arr(client: httpx.AsyncClient, base_url: str) -> bool:
    """Radarr and Sonarr answer /ping with {"status": "OK"} without a key."""
    try:
        r = await client.get(f"{base_url}/ping")
        return r.status_code == 200 and str(r.json().get("status", "")).upper() == "OK"
    except Exception:
        return False


async def test_connection(name: str, base_url: str, headers: dict, timeout: float = 30) -> Dict[str, Any]:
    """Check that base_url is the named app (Radarr or Sonarr) and the key works."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(f"{base_url}/api/v3/system/status", headers=headers)
            if response.status_code == 401:
                if await _looks_like_arr(client, base_url):
                    return _fail(f"{name} turned down the API key. Copy it again from {name}: Settings, General, API Key.")
                return _not_this_app(name)
            if response.status_code == 404:
                return _fail(f"{name} wasn't found at that address. If {name} has a base path, include it, "
                             f"like http://192.168.1.10:{PORTS.get(name, '')}/{name.lower()}.")
            if response.status_code >= 400:
                return _fail(f"{name} answered with an error. Check that it's working in its own web page, then try again.")
            try:
                data = response.json()
            except ValueError:
                return _not_this_app(name)
            if not isinstance(data, dict) or "version" not in data:
                return _not_this_app(name)
            found = str(data.get("appName") or "").strip()
            if found and found.lower() != name.lower():
                return _wrong_app(name, found)
            return {
                "success": True,
                "version": data.get("version", "Unknown"),
                "appName": found or name,
                "instanceName": data.get("instanceName", ""),
                "message": "Connection successful",
            }
    except httpx.TimeoutException:
        return _fail(f"{name} took too long to answer. Check the address and port, and that {name} is running.")
    except Exception as e:
        logger.warning("%s connection test failed: %s", name, e)
        return _fail(f"{name} didn't answer at that address. Check that it's running, and that the address and port are right.")
