"""Admin-only checks for routes that live in their own router modules.

main.py owns the real check (``_require_admin``: an admin account or a
full-access API key; with login off everyone counts as an admin, as on every
other admin route). It hands that check over with :func:`configure` when it
starts. A router used without main.py (some tests) imports main on first use
instead, so the check is never skipped.
"""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import Request

from backend.database import SessionLocal

_check: Optional[Callable] = None


def configure(check: Callable) -> None:
    """``check(request, db, action=...)`` raises when the caller isn't an admin."""
    global _check
    _check = check


def _checker() -> Callable:
    if _check is None:
        from backend import main  # noqa: F401  (configures this module on import)
    if _check is None:  # pragma: no cover - main always configures it
        raise RuntimeError("The admin check isn't set up.")
    return _check


def require(request: Request, action: str) -> None:
    """Refuse the request unless an admin (or a full-access key) made it."""
    check = _checker()
    db = SessionLocal()
    try:
        check(request, db, action=action)
    finally:
        db.close()


def admin(action: str) -> Callable:
    """A FastAPI dependency: ``dependencies=[Depends(admin("change watch folders"))]``."""

    def dependency(request: Request) -> None:
        require(request, action)

    return dependency
