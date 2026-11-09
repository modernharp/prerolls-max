"""Schedules run on the configured clock, across midnight, DST and year ends.

NeXroll's most frequent bug class (issues #6 #9 #18 #40 #50): schedules ran
hours early or late because "now" came from the container's own zone, the
browser's zone leaked into saved times, or windows that cross midnight or
New Year were evaluated as if they ended before they started.
"""
import datetime as dt
import os
import time
from unittest.mock import patch

import pytest

from backend import scheduler as module
from backend.timeutil import wall_clock
from backend.validation import parse_datetime
from tests.test_scheduler import make_schedule

UTC = dt.timezone.utc


@pytest.fixture
def sched():
    return module.Scheduler()


def next_run(sched, schedule, now):
    with patch.object(module, "_localized_now", return_value=now):
        result = sched._calculate_next_run(schedule)
    if result is not None:
        assert sched._is_schedule_active(schedule, result)
    return result


# --- the clock ---------------------------------------------------------------

@pytest.mark.parametrize("utc,zone,wall", [
    # Chicago springs forward at 02:00 CST (08:00 UTC) on 2026-03-08.
    (dt.datetime(2026, 3, 8, 7, 59), "America/Chicago", dt.datetime(2026, 3, 8, 1, 59)),
    (dt.datetime(2026, 3, 8, 8, 0), "America/Chicago", dt.datetime(2026, 3, 8, 3, 0)),
    # ...and falls back at 02:00 CDT (07:00 UTC) on 2026-11-01: 01:30 happens twice.
    (dt.datetime(2026, 11, 1, 6, 30), "America/Chicago", dt.datetime(2026, 11, 1, 1, 30)),
    (dt.datetime(2026, 11, 1, 7, 30), "America/Chicago", dt.datetime(2026, 11, 1, 1, 30)),
    # Southern hemisphere and half-hour zones.
    (dt.datetime(2026, 4, 4, 15, 59), "Australia/Sydney", dt.datetime(2026, 4, 5, 2, 59)),
    (dt.datetime(2026, 1, 1, 0, 0), "Asia/Kolkata", dt.datetime(2026, 1, 1, 5, 30)),
    # New Year arrives in Auckland while it is still the 31st in UTC.
    (dt.datetime(2026, 12, 31, 11, 0), "Pacific/Auckland", dt.datetime(2027, 1, 1, 0, 0)),
    # Unknown or empty zones fall back to UTC instead of failing.
    (dt.datetime(2026, 6, 1, 12, 0), "Mars/Olympus", dt.datetime(2026, 6, 1, 12, 0)),
    (dt.datetime(2026, 6, 1, 12, 0), "", dt.datetime(2026, 6, 1, 12, 0)),
])
def test_wall_clock_follows_the_zone_database(utc, zone, wall):
    assert wall_clock(zone, utc) == wall
    assert wall_clock(zone, utc.replace(tzinfo=UTC)) == wall


def test_the_computers_own_zone_is_ignored():
    """A container whose TZ disagrees with Settings > Time zone (issue #18)."""
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset")
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
        moment = dt.datetime(2026, 7, 1, 12, 0)
        assert wall_clock("America/New_York", moment) == dt.datetime(2026, 7, 1, 8, 0)
        expected = dt.datetime.now(UTC).astimezone(__import__("pytz").timezone("America/New_York")).replace(tzinfo=None)
        assert abs((wall_clock("America/New_York") - expected).total_seconds()) < 5
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def test_browser_zone_suffixes_are_dropped_not_converted():
    """The time typed is the time on Prerolls Max's clock, whatever the browser's zone."""
    assert parse_datetime("2026-10-31T18:30:00.000Z") == dt.datetime(2026, 10, 31, 18, 30)
    assert parse_datetime("2026-10-31T18:30:00-05:00") == dt.datetime(2026, 10, 31, 18, 30)
    assert parse_datetime("2026-10-31 18:30") == dt.datetime(2026, 10, 31, 18, 30)
    assert parse_datetime(dt.datetime(2026, 10, 31, 18, 30, tzinfo=UTC)).tzinfo is None


# --- overnight windows (issue #50) -------------------------------------------

def overnight(**kw):
    return make_schedule(type="daily", start_date=dt.datetime(2026, 1, 1), end_date=None,
                         recurrence_pattern='{"timeRange":{"start":"22:00","end":"02:00"}}', **kw)


@pytest.mark.parametrize("now,active", [
    (dt.datetime(2026, 5, 10, 21, 59), False),
    (dt.datetime(2026, 5, 10, 22, 0), True),
    (dt.datetime(2026, 5, 10, 23, 59), True),
    (dt.datetime(2026, 5, 11, 0, 0), True),
    (dt.datetime(2026, 5, 11, 1, 59), True),
    (dt.datetime(2026, 5, 11, 2, 30), False),
    (dt.datetime(2026, 5, 11, 12, 0), False),
])
def test_a_22_to_02_window_spans_midnight(sched, now, active):
    assert sched._is_schedule_active(overnight(), now) is active


def test_overnight_next_run_is_tonight_not_tomorrow(sched):
    assert next_run(sched, overnight(), dt.datetime(2026, 5, 10, 12, 0)) == dt.datetime(2026, 5, 10, 22, 0)
    # Already inside the window after midnight: it runs now.
    now = dt.datetime(2026, 5, 11, 1, 0)
    assert next_run(sched, overnight(), now) == now


def test_overnight_window_on_the_last_day_keeps_its_tail(sched):
    s = overnight()
    s.end_date = dt.datetime(2026, 5, 10, 23, 59)
    assert sched._is_schedule_active(s, dt.datetime(2026, 5, 11, 1, 0))
    assert not sched._is_schedule_active(s, dt.datetime(2026, 5, 11, 22, 30))


def test_weekly_overnight_belongs_to_the_day_it_starts(sched):
    s = make_schedule(type="weekly", recurrence_pattern=
                      '{"weekDays":["friday"],"timeRange":{"start":"22:00","end":"02:00"}}')
    friday = dt.datetime(2026, 5, 8, 23, 0)
    assert friday.strftime("%A") == "Friday"
    assert sched._is_schedule_active(s, friday)
    assert sched._is_schedule_active(s, dt.datetime(2026, 5, 9, 1, 30))  # Saturday morning tail
    assert not sched._is_schedule_active(s, dt.datetime(2026, 5, 9, 23, 0))  # Saturday night


# --- daylight saving days ------------------------------------------------------

def test_a_window_over_the_missing_spring_hour_still_runs(sched):
    """02:00-03:00 doesn't exist on 2026-03-08 in Chicago; 01:30-03:30 must still play."""
    s = make_schedule(type="daily", recurrence_pattern='{"timeRange":{"start":"01:30","end":"03:30"}}')
    before_jump = wall_clock("America/Chicago", dt.datetime(2026, 3, 8, 7, 45))  # 01:45 CST
    after_jump = wall_clock("America/Chicago", dt.datetime(2026, 3, 8, 8, 15))   # 03:15 CDT
    assert sched._is_schedule_active(s, before_jump)
    assert sched._is_schedule_active(s, after_jump)
    assert not sched._is_schedule_active(s, wall_clock("America/Chicago", dt.datetime(2026, 3, 8, 8, 45)))


def test_the_repeated_autumn_hour_plays_both_times(sched):
    s = make_schedule(type="daily", recurrence_pattern='{"timeRange":{"start":"01:00","end":"02:00"}}')
    for utc in (dt.datetime(2026, 11, 1, 6, 30), dt.datetime(2026, 11, 1, 7, 30)):
        assert sched._is_schedule_active(s, wall_clock("America/Chicago", utc))


def test_next_run_on_a_dst_day_is_a_wall_clock_time(sched):
    s = make_schedule(type="daily", recurrence_pattern='{"timeRange":{"start":"18:00","end":"23:00"}}')
    morning = wall_clock("America/Chicago", dt.datetime(2026, 3, 8, 15, 0))  # 10:00 CDT
    assert next_run(sched, s, morning) == dt.datetime(2026, 3, 8, 18, 0)


# --- year ends and leap days ---------------------------------------------------

def test_a_yearly_window_across_new_year(sched):
    s = make_schedule(type="yearly", start_date=dt.datetime(2000, 12, 15), end_date=dt.datetime(2000, 1, 15, 23, 59))
    assert sched._is_schedule_active(s, dt.datetime(2026, 12, 20, 12))
    assert sched._is_schedule_active(s, dt.datetime(2027, 1, 3, 12))
    assert sched._is_schedule_active(s, dt.datetime(2027, 1, 15, 23, 0))
    assert not sched._is_schedule_active(s, dt.datetime(2027, 1, 16, 0, 30))
    assert not sched._is_schedule_active(s, dt.datetime(2027, 2, 1, 12))
    assert next_run(sched, s, dt.datetime(2027, 2, 1, 12)) == dt.datetime(2027, 12, 15)


def test_new_years_eve_overnight_reaches_into_january(sched):
    s = make_schedule(type="yearly", start_date=dt.datetime(2000, 12, 31), end_date=dt.datetime(2000, 12, 31, 23, 59),
                      recurrence_pattern='{"timeRange":{"start":"22:00","end":"02:00"}}')
    assert sched._is_schedule_active(s, dt.datetime(2026, 12, 31, 23, 30))
    assert sched._is_schedule_active(s, dt.datetime(2027, 1, 1, 1, 30))
    assert not sched._is_schedule_active(s, dt.datetime(2027, 1, 1, 3, 0))


def test_a_leap_day_schedule_waits_for_the_next_leap_year(sched):
    s = make_schedule(type="monthly", start_date=dt.datetime(2000, 1, 1),
                      recurrence_pattern='{"months":[2],"monthDays":[29]}')
    assert next_run(sched, s, dt.datetime(2026, 3, 1)) == dt.datetime(2028, 2, 29)
    assert not sched._is_schedule_active(s, dt.datetime(2027, 2, 28, 12))
    assert not sched._is_schedule_active(s, dt.datetime(2027, 3, 1, 12))


def test_a_window_ending_on_leap_day_ends_on_the_28th_otherwise(sched):
    """Feb 20 - Feb 29 every year: in a common year it still ends with February."""
    s = make_schedule(type="yearly", start_date=dt.datetime(2000, 2, 20), end_date=dt.datetime(2000, 2, 29, 23, 59))
    assert sched._is_schedule_active(s, dt.datetime(2027, 2, 28, 22))
    assert not sched._is_schedule_active(s, dt.datetime(2027, 3, 1, 12))
    assert sched._is_schedule_active(s, dt.datetime(2028, 2, 29, 12))
