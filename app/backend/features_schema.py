"""Columns the smart features add to tables that older databases already have.

New tables (rules, exclusions, play history, watch folders...) come from
``Base.metadata.create_all``; it never adds columns to an existing table, so
those are added here, the same way main.ensure_schema does for its own.
"""
from __future__ import annotations

from typing import Callable

COLUMNS = (
    ("prerolls", "weight", "weight INTEGER DEFAULT 5"),
    ("prerolls", "loudness_lufs", "loudness_lufs FLOAT"),
    ("prerolls", "loudness_peak", "loudness_peak FLOAT"),
    ("prerolls", "loudness_lra", "loudness_lra FLOAT"),
    ("prerolls", "loudness_checked_at", "loudness_checked_at DATETIME"),
    ("prerolls", "version_of", "version_of INTEGER"),
    ("prerolls", "version_label", "version_label TEXT"),
    ("categories", "cooldown_hours", "cooldown_hours INTEGER DEFAULT 0"),
    ("categories", "system_key", "system_key TEXT"),
)


def upgrade(has_column: Callable[[str, str], bool], add_column: Callable[[str, str], None]) -> int:
    """Add whatever is missing; returns how many columns were added."""
    added = 0
    for table, column, ddl in COLUMNS:
        if not has_column(table, column):
            add_column(table, ddl)
            added += 1
    return added
