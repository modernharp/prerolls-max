import requests
import json
import os
import random
import threading
import urllib.parse
import ipaddress
from typing import Optional
from pathlib import Path
from datetime import datetime
from backend import secure_store
from backend import plex_visibility
from backend.timeutil import utcnow

def _is_dir_writable(p: str) -> bool:
    try:
        os.makedirs(p, exist_ok=True)
        test = os.path.join(p, f".nexroll_cfg_test_{os.getpid()}.tmp")
        with open(test, "w", encoding="utf-8") as f:
            f.write("ok")
        try:
            os.remove(test)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _config_dir_candidates() -> list[str]:
    cands = []
    try:
        if os.name == "nt":
            pd = os.environ.get("ProgramData")
            if pd:
                cands.append(os.path.join(pd, "Prerolls Max"))
            la = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if la:
                cands.append(os.path.join(la, "Prerolls Max"))
    except Exception:
        pass
    # Fallbacks
    cands.append(os.getcwd())
    return cands


def _resolve_config_dir() -> str:
    for d in _config_dir_candidates():
        if _is_dir_writable(d):
            return d
    # Last resort
    return os.getcwd()


def _resolve_config_path() -> str:
    return os.path.join(_resolve_config_dir(), "plex_config.json")

def _bool_env(name: str, default=None):
    try:
        v = os.environ.get(name)
        if v is None:
            return default
        s = str(v).strip().lower()
        if s in ("1","true","yes","on"):
            return True
        if s in ("0","false","no","off"):
            return False
    except Exception:
        pass
    return default

def _infer_tls_verify(url: Optional[str]) -> bool:
    """Whether to check Plex's security certificate. Always, unless turned off.

    Turn it off explicitly with PMAX_PLEX_TLS_VERIFY=0 (for a self-signed
    certificate). Prerolls Max used to skip the check silently for https
    addresses on the local network, which let anything on the network pose
    as Plex and collect the token. A plain http:// address on the local
    network, or Plex's https://...plex.direct address, needs no opt-out.
    """
    env = _bool_env("PMAX_PLEX_TLS_VERIFY", None)
    if env is not None:
        return bool(env)
    return True


def tls_error_message(url: Optional[str]) -> str:
    """What to say when Plex's certificate doesn't check out."""
    return (f"Plex's security certificate doesn't match {url or 'its address'}. Use Plex's http:// address "
            "on your network, or its https://...plex.direct address. To skip the check anyway, "
            "set PMAX_PLEX_TLS_VERIFY=0.")


def unsafe_for_plex(path: str) -> bool:
    """Plex splits its intro list on commas (in order) and semicolons (random),
    so a file or folder name with either can't be in the list."""
    return "," in (path or "") or ";" in (path or "")



class PlexConnector:
    def __init__(self, url: Optional[str], token: Optional[str] = None):
        self.url = url.rstrip('/') if url else None
        self.token = token
        # Look for config file in current directory first, then parent directory
        self.config_file = self._find_config_file()
        self.headers = {}
        self._verify = _infer_tls_verify(self.url)
        # Outcome of the Plex path check made by the last set_preroll() call.
        self.last_visibility: Optional[plex_visibility.GateResult] = None
        # Why the last set_preroll() failed, in plain words (None after success).
        self.last_error: Optional[str] = None
        # What the last set_preroll() had to leave out to fit, if anything.
        self.last_shortened: Optional[str] = None

        # Try to load stable token from config file if no token provided
        if not token:
            self.load_stable_token()

        if self.token:
            self.headers = {'X-Plex-Token': self.token}

    def _find_config_file(self):
        """
        Resolve a writable plex_config.json path.
        Migrate legacy config from cwd/parent if present and new path missing.
        """
        new_path = _resolve_config_path()
        # Migrate legacy locations once
        try:
            legacy_cands = []
            try:
                cwd = os.getcwd()
                legacy_cands.append(os.path.join(cwd, "plex_config.json"))
                legacy_cands.append(os.path.join(os.path.dirname(cwd), "plex_config.json"))
            except Exception:
                pass
            if not os.path.exists(new_path):
                for lp in legacy_cands:
                    try:
                        if lp and os.path.exists(lp):
                            os.makedirs(os.path.dirname(new_path), exist_ok=True)
                            with open(lp, "rb") as src, open(new_path, "wb") as dst:
                                dst.write(src.read())
                            break
                    except Exception:
                        continue
        except Exception:
            pass
        return new_path

    def load_stable_token(self):
        """Load stable token from secure store (preferred). Migrate from legacy plex_config.json if present."""
        try:
            # 1) Preferred: secure store
            try:
                tok = secure_store.get_plex_token()
            except Exception:
                tok = None

            if tok:
                self.token = tok
                self.headers = {'X-Plex-Token': self.token}
                print("Loaded Plex token from secure store (Windows Credential Manager)")
                return True

            # 2) Legacy fallback and one-time migration from plex_config.json
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                legacy = cfg.get('plex_token')
                if legacy:
                    print(f">>> UPGRADE DETECTED: Found legacy Plex token in {self.config_file}")
                    print(f">>> MIGRATING: Moving token to secure store (Windows Credential Manager)...")
                    if secure_store.set_plex_token(legacy):
                        # Rewrite legacy file without the plaintext token
                        try:
                            cfg.pop('plex_token', None)
                            cfg['token_migrated'] = True
                            cfg['migration_date'] = utcnow().isoformat() + "Z"
                            cfg['token_length'] = len(legacy)
                            cfg.setdefault('note', 'Token migrated to secure store; file contains no secrets')
                            with open(self.config_file, 'w', encoding='utf-8') as wf:
                                json.dump(cfg, wf, indent=2)
                            print(f">>> MIGRATION SUCCESS: Token securely stored in Windows Credential Manager")
                            print(f">>> CONFIG UPDATED: Sanitized {self.config_file} (no plaintext secrets)")
                        except Exception as e:
                            print(f">>> MIGRATION WARNING: Token migrated but config rewrite failed: {e}")
                            pass
                        self.token = legacy
                        self.headers = {'X-Plex-Token': self.token}
                        return True
                    else:
                        print(f">>> MIGRATION FAILED: Could not access secure store. Token remains in {self.config_file}")
                        # Fall back to using the legacy token
                        self.token = legacy
                        self.headers = {'X-Plex-Token': self.token}
                        return True
                else:
                    print(f"ℹ No token found in {self.config_file} (already migrated or not configured)")
            else:
                print("ℹ No plex_config.json found; token should be in secure store or needs manual entry")
        except Exception as e:
            print(f"Error loading Plex token: {e}")

        return False

    def save_stable_token(self, token: str):
        """Persist token to secure store. Writes a sanitized plex_config.json without secrets for diagnostics."""
        try:
            ok = False
            try:
                ok = secure_store.set_plex_token(token)
            except Exception:
                ok = False

            if not ok:
                print("Secure store not available; refusing to write plaintext token")
                return False

            # Optionally write a sanitized config file (no secrets) for tooling/diagnostics
            try:
                cfg_dir = os.path.dirname(self.config_file) or "."
                os.makedirs(cfg_dir, exist_ok=True)
                cfg = {
                    "setup_date": utcnow().isoformat() + "Z",
                    "note": "Token saved to secure store; this file contains no secrets",
                    "token_length": len(token)
                }
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
            except Exception:
                pass

            self.token = token
            self.headers = {'X-Plex-Token': self.token}
            print("Stable token saved to secure store")
            return True
        except Exception as e:
            print(f"Error saving token: {e}")
            return False

    def test_connection(self) -> bool:
        try:
            # Guard against missing/invalid URL
            if not self.url or not isinstance(self.url, str):
                return False

            # Log minimal token preview without assuming length
            token_preview = "<none>"
            try:
                if self.token:
                    token_preview = (self.token[:10] + "...") if len(self.token) > 10 else str(self.token)
            except Exception:
                token_preview = "<error>"

            print(f"Testing Plex connection to: {self.url}")
            print(f"Using token: {token_preview}")

            response = requests.get(f"{self.url}/", headers=self.headers, timeout=10, verify=self._verify)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
        except Exception:
            return False

    def get_server_info(self) -> Optional[dict]:
        """
        Return a normalized dict with Plex server info if reachable.
        Never raises; returns None on failure/missing URL.
        """
        try:
            if not self.url or not isinstance(self.url, str):
                return None

            response = requests.get(f"{self.url}/", headers=self.headers, timeout=10, verify=self._verify)
            if response.status_code == 200:
                # Parse XML response to get server info
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(response.content)
                    server_info = {
                        "connected": True,
                        "status": "OK",
                        "name": root.get('friendlyName') or 'Unknown Server',
                        "version": root.get('version') or 'Unknown',
                        "platform": root.get('platform') or 'Unknown',
                        "machine_identifier": root.get('machineIdentifier') or 'Unknown'
                    }
                    return server_info
                except Exception:
                    # If XML parse fails, still treat server as reachable
                    return {"connected": True}
            return None
        except Exception:
            return None

    # Plex answers 400 when the request line gets longer than about 8000
    # characters, so the encoded list is kept under this.
    _PLEX_MAX_QUERY_URL_LEN = 8000
    _PLEX_SAFE_PREROLL_LEN = 7500

    # The one server preference Plex reads its intro list from. Prerolls Max
    # used to try six spellings with three request styles each; only this one
    # exists, and the guessing hid the real reason when a write failed.
    PREROLL_PREF = "CinemaTrailersPrerollID"

    # A random ("a;b;c") list too long for Plex is cut to a random subset that
    # is kept for this long, so Plex isn't sent a new subset every cycle.
    _CHUNK_ROTATION_HOURS = 8
    _chunk_lock = threading.Lock()
    _chunk_cache_value: Optional[str] = None
    _chunk_cache_source: Optional[str] = None
    _chunk_cache_time: Optional[datetime] = None

    @staticmethod
    def _encoded(value: str) -> str:
        return urllib.parse.quote(value, safe=":/\\;, ")

    def _fits(self, value: str) -> bool:
        return len(f"{self.url}/:/prefs?{self.PREROLL_PREF}=") + len(self._encoded(value)) <= self._PLEX_MAX_QUERY_URL_LEN

    def _build_chunked_subset(self, preroll_path: str, delimiter: str = ";") -> Optional[str]:
        """A shorter list that fits what Plex accepts, or None if it can't help.

        Comma lists play in order, so they keep their first entries in order
        (they used to be shuffled, which scrambled every playlist). Semicolon
        lists are a pool Plex picks one from, so a random subset stands in for
        the whole pool; it is kept for _CHUNK_ROTATION_HOURS, under a lock
        because the scheduler and the web requests share it.
        """
        paths = [p.strip() for p in preroll_path.split(delimiter) if p.strip()]
        if len(paths) <= 1:
            return None
        budget = self._PLEX_SAFE_PREROLL_LEN

        def take(candidates):
            chosen, used = [], 0
            for p in candidates:
                cost = len(self._encoded(p)) + (len(delimiter) if chosen else 0)
                if used + cost > budget:
                    if delimiter == ",":
                        break
                    continue
                chosen.append(p)
                used += cost
            return delimiter.join(chosen or paths[:1])

        if delimiter == ",":
            return take(paths)

        cls = type(self)
        now = datetime.now()
        with cls._chunk_lock:
            fresh = (cls._chunk_cache_value is not None
                     and cls._chunk_cache_source == preroll_path
                     and cls._chunk_cache_time is not None
                     and (now - cls._chunk_cache_time).total_seconds() < cls._CHUNK_ROTATION_HOURS * 3600)
            if fresh:
                return cls._chunk_cache_value
            shuffled = list(paths)
            random.shuffle(shuffled)
            result = take(shuffled)
            cls._chunk_cache_value = result
            cls._chunk_cache_source = preroll_path
            cls._chunk_cache_time = now
            return result

    def visibility_summary(self) -> Optional[dict]:
        """The last path check in a form API responses can carry."""
        g = self.last_visibility
        if g is None:
            return None
        return {
            "action": g.action,
            "message": g.message,
            "checked": len(g.results),
            "missing": [{"path": r["path"], "reason": r["reason"]} for r in g.missing][:25],
        }

    def set_preroll(self, preroll_path: str) -> bool:
        """Write the intro list to Plex's CinemaTrailersPrerollID and read it back.

        Before anything is written, Plex is asked whether it can see each file
        (see plex_visibility). Files it cannot see are left out; if it can see
        none of them, nothing is written and Plex keeps its current prerolls,
        which is reported as a failure with the reason in last_visibility.
        When the check cannot run, the value is written as it is.

        A list too long for Plex is shortened first (see _build_chunked_subset)
        and last_shortened says how. On failure last_error says why, plainly.
        """
        self.last_visibility = None
        self.last_error = None
        self.last_shortened = None
        self.left_to_nexroll = False
        try:
            from backend import coexist
            if coexist.plex_url_left_to_nexroll(self.url):
                # Settings > Moving from NeXroll: this Plex server is NeXroll's.
                # Writing its one intro list would undo NeXroll's, so leave it.
                self.left_to_nexroll = True
                print(f"INFO: NeXroll manages intros on the Plex server at {self.url}; its list wasn't changed")
                return True
        except Exception:
            pass
        if preroll_path:
            try:
                gate = plex_visibility.gate_preroll_value(
                    plex_visibility.PlexFiles.from_connector(self), preroll_path)
                self.last_visibility = gate
                if gate.action in ("withheld", "filtered"):
                    print(f"WARNING: {gate.message}")
                    for r in gate.missing[:10]:
                        print(f"  Plex cannot see {r['path']}: {r['reason']}")
                if gate.action == "withheld":
                    self.last_error = gate.message
                    return False
                if gate.action == "filtered":
                    preroll_path = gate.value
            except Exception as e:
                print(f"INFO: Plex path check skipped ({e}); writing the preroll unchecked")
        try:
            value = preroll_path or ""
            if value and not self._fits(value):
                delimiter = "," if "," in value and ";" not in value else ";"
                total = len([p for p in value.split(delimiter) if p.strip()])
                shorter = self._build_chunked_subset(value, delimiter)
                if shorter and shorter != value:
                    kept = len([p for p in shorter.split(delimiter) if p.strip()])
                    self.last_shortened = (
                        f"Plex takes a list of about 7,500 characters, so only the first {kept} of {total} "
                        "intros in this playlist play on Plex." if delimiter == "," else
                        f"Plex takes a list of about 7,500 characters, so Plex picks from {kept} of these "
                        f"{total} intros, changing every {self._CHUNK_ROTATION_HOURS} hours.")
                    print(f"INFO: {self.last_shortened}")
                    value = shorter
            ok = self._try_set_preroll_value(value)
            if ok:
                try:
                    from backend import nexroll_detect
                    nexroll_detect.note_plex_written(self.url, value)
                except Exception:
                    pass
            if not ok and not self.last_error:
                self.last_error = "Plex didn't take the new intro list."
            return ok
        except requests.exceptions.SSLError:
            self.last_error = tls_error_message(self.url)
        except requests.exceptions.Timeout:
            self.last_error = f"Plex didn't answer at {self.url} in time."
        except requests.exceptions.ConnectionError:
            self.last_error = f"Plex didn't answer at {self.url}."
        except Exception as e:
            print(f"Unexpected error setting Plex preroll: {e}")
            self.last_error = "Something went wrong while changing Plex's intro list. The log has the details."
        print(f"FAILURE: {self.last_error}")
        return False

    def _try_set_preroll_value(self, preroll_path: str) -> bool:
        """One PUT of CinemaTrailersPrerollID, then one read back to confirm.

        Returns True only when Plex reports the new value (or can't be read
        back after accepting it); otherwise leaves the reason in last_error.
        """
        response = requests.put(
            f"{self.url}/:/prefs?{self.PREROLL_PREF}={self._encoded(preroll_path)}",
            headers=self.headers, timeout=10, verify=self._verify)
        status = getattr(response, "status_code", 0)
        if status in (401, 403):
            self.last_error = ("Plex turned down the token when Prerolls Max changed the intro list. Sign in to "
                               "Plex again under Media Servers with the server owner's account.")
            return False
        if status == 400:
            self.last_error = "Plex refused the intro list (HTTP 400). It is probably too long; use fewer intros."
            return False
        if status not in (200, 201, 204):
            self.last_error = f"Plex answered HTTP {status} when Prerolls Max changed the intro list."
            return False
        current = self._read_preroll_pref()
        if current is None:
            # Written, but not readable back (an older server, a hiccup). Trust the 2xx.
            return True
        if current == preroll_path:
            return True
        self.last_error = ("Plex accepted the change but still shows a different intro list. Another app may have "
                           "changed it at the same moment, or the token isn't the server owner's.")
        return False

    def _read_preroll_pref(self) -> Optional[str]:
        """CinemaTrailersPrerollID as Plex reports it, or None if it can't be read."""
        try:
            response = requests.get(f"{self.url}/:/prefs", headers=self.headers, timeout=10, verify=self._verify)
            if getattr(response, "status_code", 0) != 200:
                return None
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            for setting in root.iter("Setting"):
                if setting.get("id") == self.PREROLL_PREF:
                    return setting.get("value", "")
        except Exception:
            return None
        return None


    def get_current_preroll(self) -> Optional[str]:
        """Plex's current intro list ("" when empty), or None if it can't be read."""
        value = self._read_preroll_pref()
        if value is not None:
            try:
                from backend import nexroll_detect
                nexroll_detect.note_plex_read(self.url, value)
            except Exception:
                pass
        return value

    # Plex "Cinema Trailers" server preferences that Prerolls Max exposes for control.
    # Values/types are read live from /:/prefs so we reflect the server's real
    # state (and whatever enum options it advertises) rather than hardcoding.
    CINEMA_TRAILER_PREF_IDS = (
        "CinemaTrailersType",                 # enum: choose trailers from (e.g. 0=all, 1=unwatched)
        "CinemaTrailersFromLibrary",          # bool: include from movies in my library
        "CinemaTrailersFromTheater",          # bool: new/upcoming in theaters (Plex Pass)
        "CinemaTrailersFromBluRay",           # bool: new/upcoming on Blu-ray (Plex Pass)
        "CinemaTrailersAlwaysIncludeEnglish", # bool: always include English trailers for movies not in library
    )

    # Where Plex finds trailers of its own. With every one off Plex has no
    # trailers to add, so an app set to "Play 1 before movie" plays the preroll
    # list and nothing else. Plex's newer apps (Apple TV and iOS 2026.18, the
    # Android TV 2026.17 beta) skip prerolls on "Play Pre-roll Only" but still
    # play them on "Play 1", so this is the setup that works on every app.
    CINEMA_TRAILER_SOURCE_IDS = (
        "CinemaTrailersFromLibrary",
        "CinemaTrailersFromTheater",
        "CinemaTrailersFromBluRay",
    )

    def disable_trailer_sources(self) -> Optional[dict]:
        """
        Switch off every trailer source the server advertises and leave the
        other Cinema Trailers settings alone. Returns {"changed": [...],
        "failed": [...]} with setting ids, or None if the prefs can't be read.
        Sources that are already off are not written.
        """
        prefs = self.get_cinema_trailer_prefs()
        if prefs is None:
            return None
        changed, failed = [], []
        for sid in self.CINEMA_TRAILER_SOURCE_IDS:
            pref = prefs.get(sid)
            if pref is None or str(pref.get("value", "")).strip().lower() not in ("1", "true"):
                continue
            (changed if self.set_pref(sid, False) else failed).append(sid)
        return {"changed": changed, "failed": failed}

    def get_cinema_trailer_prefs(self) -> Optional[dict]:
        """
        Read the Cinema Trailers preferences from the Plex server's /:/prefs.
        Returns a dict keyed by setting id with {value, type, enumValues, label,
        hidden, advanced} for each CinemaTrailers* setting the server reports,
        or None on failure. Only settings the server actually advertises are
        included (so non-Plex-Pass servers simply omit the Plex Pass ones).
        """
        if not self.url:
            return None
        try:
            import xml.etree.ElementTree as ET
            prefs_url = f"{self.url}/:/prefs"
            response = requests.get(prefs_url, headers=self.headers, timeout=10, verify=self._verify)
            if response.status_code != 200:
                print(f"get_cinema_trailer_prefs: prefs returned {response.status_code}")
                return None
            root = ET.fromstring(response.content)
            out = {}
            for setting in root.findall('.//Setting'):
                sid = setting.get('id', '')
                if sid in self.CINEMA_TRAILER_PREF_IDS:
                    out[sid] = {
                        "value": setting.get('value', ''),
                        "type": setting.get('type', ''),
                        "label": setting.get('label', sid),
                        "enumValues": setting.get('enumValues', ''),
                        "hidden": setting.get('hidden', '0') in ('1', 'true', 'True'),
                        "advanced": setting.get('advanced', '0') in ('1', 'true', 'True'),
                    }
            return out
        except Exception as e:
            print(f"get_cinema_trailer_prefs error: {e}")
            return None

    def set_pref(self, key: str, value) -> bool:
        """
        Set a single Plex server preference via PUT /:/prefs?key=value and verify
        it took. Booleans are coerced to Plex's lowercase 'true'/'false'.
        """
        if not self.url or not key:
            return False
        try:
            if isinstance(value, bool):
                value_str = "true" if value else "false"
            else:
                value_str = str(value)
            prefs_url = f"{self.url}/:/prefs"
            encoded = urllib.parse.quote(value_str, safe="")
            resp = requests.put(
                f"{prefs_url}?{key}={encoded}",
                headers=self.headers,
                timeout=10,
                verify=self._verify,
            )
            if resp.status_code not in (200, 201, 204):
                print(f"set_pref {key}={value_str} failed: {resp.status_code} {resp.text[:120]}")
                return False
            # Verify by re-reading. Plex stores boolean prefs as '1'/'0' in
            # /:/prefs even though it accepts 'true'/'false' on the PUT, so a raw
            # string compare ('1' == 'true') would wrongly report failure even
            # though the change applied. Compare booleans semantically.
            try:
                import xml.etree.ElementTree as ET
                check = requests.get(prefs_url, headers=self.headers, timeout=10, verify=self._verify)
                if check.status_code == 200:
                    root = ET.fromstring(check.content)
                    truthy = {"1", "true", "on", "yes"}
                    for setting in root.findall('.//Setting'):
                        if setting.get('id', '') == key:
                            actual = str(setting.get('value', '')).strip().lower()
                            if isinstance(value, bool):
                                return (actual in truthy) == value
                            return actual == value_str.lower()
            except Exception:
                pass
            # If we couldn't verify, trust the 2xx
            return True
        except Exception as e:
            print(f"set_pref {key} error: {e}")
            return False

    def get_preroll(self) -> str:
        """Plex's current intro list, or "" when empty or unreadable."""
        value = self._read_preroll_pref()
        if value is not None:
            try:
                from backend import nexroll_detect
                nexroll_detect.note_plex_read(self.url, value)
            except Exception:
                pass
        return value or ""
