"""
Prerolls Max backend package initializer.

This file ensures Python treats the 'backend' directory as a proper package
so absolute imports like 'from backend.database import SessionLocal' resolve
correctly in both source and PyInstaller-frozen environments.
"""

# NEXROLL_* settings from a NeXroll install keep working as PMAX_*.
try:
    from backend.brand import apply_env_aliases as _apply_env_aliases
except ImportError:  # imported as a top-level module in frozen builds
    from brand import apply_env_aliases as _apply_env_aliases
_apply_env_aliases()

__all__ = [
    "database",
    "models",
    "scheduler",
    "plex_connector",
]