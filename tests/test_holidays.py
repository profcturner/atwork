import datetime as dt
from pathlib import Path

import pytest

from atwork.holidays import HolidayFileError, load_ics, parse_ics, parse_text

DATA = Path(__file__).parent / "data"
D = dt.date


def test_ics_all_day_events():
    dates = load_ics(DATA / "bank-holidays.ics")
    assert D(2026, 12, 25) in dates
    assert D(2026, 12, 26) not in dates  # DTEND is exclusive
    assert D(2026, 12, 28) in dates
    assert D(2026, 3, 17) in dates


def test_ics_multi_day_event():
    dates = load_ics(DATA / "bank-holidays.ics")
    assert {D(2026, 8, 3), D(2026, 8, 4), D(2026, 8, 5)} <= dates
    assert D(2026, 8, 6) not in dates


def test_ics_ignores_timed_events():
    assert D(2026, 11, 2) not in load_ics(DATA / "bank-holidays.ics")


def test_ics_without_dtend_is_one_day():
    text = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20270101\nEND:VEVENT\nEND:VCALENDAR\n"
    assert parse_ics(text) == {D(2027, 1, 1)}


def test_ics_crlf_line_endings():
    text = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20270101\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    assert parse_ics(text) == {D(2027, 1, 1)}


def test_ics_rejects_non_calendar():
    with pytest.raises(HolidayFileError):
        parse_ics("2026-12-25\n")


def test_ics_missing_file():
    with pytest.raises(HolidayFileError, match="cannot read"):
        load_ics(DATA / "nope.ics")


def test_text_single_dates_and_comments():
    text = """
    # a comment
    2026-12-29
    2026-08-14   Staff day  # trailing comment
    """
    assert parse_text(text) == {D(2026, 12, 29), D(2026, 8, 14)}


def test_text_ranges_are_inclusive():
    dates = parse_text("2026-12-24..2027-01-02\n")
    assert len(dates) == 10
    assert min(dates) == D(2026, 12, 24)
    assert max(dates) == D(2027, 1, 2)


def test_text_range_with_spaces():
    assert parse_text("2026-12-24 .. 2026-12-25") == {D(2026, 12, 24), D(2026, 12, 25)}


@pytest.mark.parametrize("bad", ["25/12/2026", "2026-13-01", "2026-12-25..2026-12-01", "tomorrow"])
def test_text_bad_lines(bad):
    with pytest.raises(HolidayFileError):
        parse_text(bad, "h.txt")
