"""The server-specific steps of "Test connection" on the Media Servers page."""
from __future__ import annotations

from typing import Optional

from backend import media_servers as ms, server_probe


def _step(sid: str, title: str, state: str, detail: Optional[str] = None, link: Optional[dict] = None) -> dict:
    return {"id": sid, "title": title, "state": state, "detail": detail, "link": link}


def mapping_link(row) -> dict:
    return {"to": f"/settings/advanced/folder-mapping?server={row.id}", "label": "Set up folder mapping"}


def plex_files_step(db, row, target) -> dict:
    """Can this Plex see the files in its intro list?"""
    from backend import plex_visibility
    from backend.plex_connector import PlexConnector
    name = ms.label(row)
    title = f"{name} can see your intro files"
    connector = PlexConnector(target.url, target.token)
    value = connector.get_current_preroll()
    if value is None:
        return _step("files", title, "warn", f"{name} stopped answering during the check. Try again in a minute.")
    if not value.strip():
        return _step("files", title, "warn",
                     f"Nothing has been sent to {name} yet, so there's nothing to check. Make a schedule or turn on "
                     "default intros, then test again.")
    try:
        files = plex_visibility.PlexFiles.from_connector(connector, max_calls=60, time_budget=20)
        result = plex_visibility.check_value(files, value)
    except Exception:
        return _step("files", title, "warn", f"{name} didn't let Prerolls Max look at its folders just now.")
    if result.action == "ok":
        return _step("files", title, "ok")
    missing = len(result.missing)
    return _step("files", title, "warn",
                 f"{name} can't find {missing} of the intro files where Prerolls Max says they are. This is common "
                 "when either one runs in Docker: each Plex server needs its own folder mapping.",
                 mapping_link(row))


def plugin_steps(db, row, target, signed_in: bool) -> list:
    """Is the plugin installed, set up, and has it asked for intros?"""
    from backend.routers.capabilities import _plugin_state, plugin_rows_for
    name = ms.label(row)
    steps = []
    if not signed_in:
        return [_step("plugin", f"The Prerolls Max plugin is installed in {name}", "skipped"),
                _step("asked", "The plugin has asked Prerolls Max for an intro", "skipped")]
    info = server_probe.plugin_info(target)
    if info.get("installed") is None:
        steps.append(_step("plugin", f"The Prerolls Max plugin is installed in {name}", "warn",
                           f"{name} won't list its plugins for this API key. Use a key made by an administrator."))
    elif not info["installed"]:
        steps.append(_step("plugin", f"The Prerolls Max plugin is installed in {name}", "fail",
                           f"{name} doesn't have the plugin yet. Without it, {name} can't ask which intro to play. "
                           "Follow the plugin steps on this server's card."))
        return steps + [_step("asked", "The plugin has asked Prerolls Max for an intro", "skipped")]
    else:
        version = f"Version {info['version']}" if info.get("version") else None
        steps.append(_step("plugin", f"The Prerolls Max plugin is installed in {name}", "ok", version))
        if info.get("configured") is False:
            steps.append(_step("setup", "The plugin knows where Prerolls Max is", "warn",
                               "Press \"Set up the plugin for me\" on this server's card."))
    count = len(ms.ordered(db, row.type))
    state = _plugin_state(row.type, plugin_rows_for(row.type, row.id, row.server_identifier, count == 1))
    if state.get("connected"):
        steps.append(_step("asked", "The plugin has asked Prerolls Max for an intro", "ok",
                           f"Plugin {state['version']}" if state.get("version") else None))
    else:
        steps.append(_step("asked", "The plugin has asked Prerolls Max for an intro", "warn",
                           f"Not yet. Play any movie in {name}; the plugin asks for an intro when it starts."))
    return steps
