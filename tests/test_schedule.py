from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ccdrop.models import Schedule
from ccdrop.schedule import in_window

WARSAW = ZoneInfo("Europe/Warsaw")
DAYTIME = Schedule(hours=(8, 22), before=2, after=3)


def warsaw(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 3, hour, minute, tzinfo=WARSAW)


def test_last_minute_before_the_hour_is_inside():
    assert in_window(DAYTIME, warsaw(8, 59)) is True


def test_second_minute_after_the_hour_is_inside():
    assert in_window(DAYTIME, warsaw(9, 2)) is True


def test_last_minute_after_the_hour_is_inside():
    assert in_window(DAYTIME, warsaw(9, 3)) is True


def test_first_minute_past_the_window_is_outside():
    assert in_window(DAYTIME, warsaw(9, 4)) is False


def test_half_past_the_hour_is_outside():
    assert in_window(DAYTIME, warsaw(9, 30)) is False


def test_minute_before_the_window_opens_is_outside():
    assert in_window(DAYTIME, warsaw(8, 57)) is False


def test_minute_fiftyeight_belongs_to_the_next_hour():
    assert in_window(Schedule(hours=(9, 9), before=2, after=3), warsaw(8, 58)) is True


def test_window_of_the_closing_hour_is_inside():
    assert in_window(DAYTIME, warsaw(21, 58)) is True


def test_window_past_the_closing_hour_is_outside():
    assert in_window(DAYTIME, warsaw(22, 58)) is False


def test_window_of_the_opening_hour_is_inside():
    assert in_window(DAYTIME, warsaw(7, 58)) is True


def test_hour_before_the_opening_hour_is_outside():
    assert in_window(DAYTIME, warsaw(6, 59)) is False


def test_summer_utc_moment_is_judged_in_warsaw_time():
    assert in_window(DAYTIME, datetime(2026, 8, 3, 6, 59, tzinfo=UTC)) is True


def test_winter_utc_moment_is_judged_in_warsaw_time():
    assert in_window(DAYTIME, datetime(2026, 1, 15, 6, 59, tzinfo=UTC)) is True


def test_zero_margins_keep_the_full_hour_inside():
    assert in_window(Schedule(hours=(8, 22), before=0, after=0), warsaw(9, 0)) is True


def test_zero_margins_push_the_next_minute_outside():
    assert in_window(Schedule(hours=(8, 22), before=0, after=0), warsaw(9, 1)) is False
