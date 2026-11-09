"""Glue between the plugin route and the smart features.

main.py hands these to ``plugin_v2.configure`` so the route stays free of the
database details: the never-play list and rule set (intro_rules.py), play
history (play_history.py), and the "one sitting" gap (smart_settings.py).
"""
from __future__ import annotations

import logging
from typing import Optional

from backend import intro_rules, play_history, smart_settings

logger = logging.getLogger("prerollsmax.features")


def smart_intros(db, *, facts: dict, server_type: str = "") -> Optional[dict]:
    """The never-play list, then the rule set; None lets the schedules decide."""
    if db is None:
        return None
    return intro_rules.resolve(db, facts, smart_settings.get_all(db))


def rule_pool(db) -> list:
    return intro_rules.pool_paths(db) if db is not None else []


def on_answer(db, *, facts: dict, server_type: str, server_name: str, items: list, reason: str,
              excluded: bool = False, rule_name: Optional[str] = None) -> None:
    if db is None:
        return
    settings = smart_settings.get_all(db)
    try:
        play_history.record_plugin_answer(db, facts=facts, server_type=server_type, server_name=server_name,
                                          items=items, reason=reason, excluded=excluded, rule_name=rule_name,
                                          history=bool(settings.get("history_enabled", True)))
    except Exception:
        db.rollback()
        raise


def binge_hours() -> int:
    try:
        return int(smart_settings.get("binge_window_hours") or 4)
    except (TypeError, ValueError):
        return 4
