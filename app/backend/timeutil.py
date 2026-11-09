"""The current UTC time without datetime.utcnow(), which Python 3.12 deprecated.

Prerolls Max keeps naive UTC datetimes everywhere (database columns, the values it
compares them with), so utcnow() returns the same naive value utcnow() did.
datetime.now(timezone.utc) on its own is timezone-aware, and comparing it with
a stored naive value raises TypeError.
"""
import datetime


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def wall_clock(tz_name, now_utc=None) -> datetime.datetime:
    """Naive wall-clock time in the IANA zone ``tz_name`` (Settings > Time zone).

    Schedules store naive local times and are compared with this. It is worked
    out from the UTC clock and the zone database, never from the computer's own
    zone, which in containers is often UTC whatever TZ says (issues #9, #18).
    An unknown or empty zone means UTC. ``now_utc`` (naive UTC or aware) is for
    tests; daylight saving changes come from the zone database.
    """
    import pytz

    try:
        tz = pytz.timezone(str(tz_name or "UTC").strip() or "UTC")
    except Exception:
        tz = pytz.utc
    if now_utc is None:
        moment = datetime.datetime.now(datetime.timezone.utc)
    elif now_utc.tzinfo is None:
        moment = now_utc.replace(tzinfo=datetime.timezone.utc)
    else:
        moment = now_utc
    return moment.astimezone(tz).replace(tzinfo=None)
