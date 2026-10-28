"""Loading holiday dates from .ics files and plain text files.

Everything here uses only the Python standard library.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path


class HolidayFileError(Exception):
    """Raised when a holiday source cannot be read or understood."""


def _date_range(start: dt.date, end_inclusive: dt.date) -> set[dt.date]:
    if end_inclusive < start:
        raise ValueError(f"range ends ({end_inclusive}) before it starts ({start})")
    days = (end_inclusive - start).days
    return {start + dt.timedelta(days=i) for i in range(days + 1)}


# --------------------------------------------------------------------------
# Plain text holidays file
# --------------------------------------------------------------------------

_DATE = r"\d{4}-\d{2}-\d{2}"
_TEXT_LINE = re.compile(rf"^({_DATE})(?:\s*\.\.\s*({_DATE}))?(?:\s+.*)?$")


def parse_text(text: str, source: str = "<text>") -> set[dt.date]:
    """Parse a holidays text file.

    Format, one entry per line:

        # Comments start with a hash; blank lines are ignored
        2026-12-29                      a single day
        2026-12-24..2027-01-02          an inclusive range
        2026-08-14  Staff day           anything after the date is ignored
    """
    dates: set[dt.date] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = _TEXT_LINE.match(line)
        if not match:
            raise HolidayFileError(
                f"{source}:{lineno}: expected YYYY-MM-DD or "
                f"YYYY-MM-DD..YYYY-MM-DD, got {raw.strip()!r}"
            )
        try:
            start = dt.date.fromisoformat(match.group(1))
            end = dt.date.fromisoformat(match.group(2)) if match.group(2) else start
            dates |= _date_range(start, end)
        except ValueError as exc:
            raise HolidayFileError(f"{source}:{lineno}: {exc}") from None
    return dates


# --------------------------------------------------------------------------
# iCalendar (.ics)
# --------------------------------------------------------------------------


def _unfold(text: str) -> list[str]:
    """Undo RFC 5545 line folding (continuation lines start with space/tab)."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_ics_value(line: str) -> tuple[str, dict[str, str], str]:
    """Split 'NAME;PARAM=X:value' into (NAME, {PARAM: X}, value)."""
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    param_map = {}
    for p in params:
        k, _, v = p.partition("=")
        param_map[k.upper()] = v
    return name.upper(), param_map, value.strip()


def _ics_date(value: str, params: dict[str, str]) -> dt.date | None:
    """Return a date for an all-day value, or None for a timed value."""
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d").date()
    return None


def parse_ics(text: str, source: str = "<ics>") -> set[dt.date]:
    """Return every date covered by an all-day event in an iCalendar file.

    Timed events (meetings etc.) are ignored: only all-day events count as
    holidays. Recurring events (RRULE) are not expanded; each occurrence
    must be listed, as the gov.uk bank holiday feeds do.
    """
    dates: set[dt.date] = set()
    in_event = False
    start = end = None
    timed = False
    saw_calendar = False

    for line in _unfold(text):
        if not line.strip():
            continue
        name, params, value = _parse_ics_value(line)
        if name == "BEGIN" and value.upper() == "VCALENDAR":
            saw_calendar = True
        elif name == "BEGIN" and value.upper() == "VEVENT":
            in_event, start, end, timed = True, None, None, False
        elif name == "END" and value.upper() == "VEVENT":
            if in_event and start is not None and not timed:
                # DTEND is exclusive for all-day events; default is one day.
                last = (end - dt.timedelta(days=1)) if end and end > start else start
                dates |= _date_range(start, last)
            in_event = False
        elif in_event and name in ("DTSTART", "DTEND"):
            try:
                day = _ics_date(value, params)
            except ValueError:
                raise HolidayFileError(f"{source}: bad {name} value {value!r}") from None
            if day is None:
                timed = True
            elif name == "DTSTART":
                start = day
            else:
                end = day

    if not saw_calendar:
        raise HolidayFileError(f"{source}: does not look like an iCalendar file")
    return dates


# --------------------------------------------------------------------------
# File loading
# --------------------------------------------------------------------------


def _read(path: str | Path) -> str:
    try:
        return Path(path).expanduser().read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise HolidayFileError(f"cannot read {path}: {exc.strerror or exc}") from None


def load_ics(path: str | Path) -> set[dt.date]:
    return parse_ics(_read(path), str(path))


def load_text(path: str | Path) -> set[dt.date]:
    return parse_text(_read(path), str(path))
