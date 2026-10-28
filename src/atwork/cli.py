"""Command line interface for atwork.

Exit codes:
    0  it is working time (so `atwork && send-email` sends)
    1  it is not working time
    2  error (bad arguments, unreadable file, ...) - also blocks `&&`
"""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .holidays import HolidayFileError, load_ics, load_text

AT_WORK = 0
NOT_AT_WORK = 1
ERROR = 2

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_CONFIG_PATHS = [
    Path("~/.config/atwork/atwork.conf"),
    Path("/etc/atwork.conf"),
]


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    days: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})
    start: dt.time = dt.time(8, 0)
    end: dt.time = dt.time(17, 0)
    ics: list[str] = field(default_factory=list)
    holidays: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------


def parse_days(spec: str) -> set[int]:
    """Parse 'mon-fri', 'mon,wed,fri', 'mon-thu,sat' into weekday numbers."""
    days: set[int] = set()
    for part in spec.lower().replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                ia, ib = DAY_NAMES.index(a[:3]), DAY_NAMES.index(b[:3])
                if ia > ib:
                    raise ConfigError(f"day range {part!r} runs backwards")
                days.update(range(ia, ib + 1))
            else:
                days.add(DAY_NAMES.index(part[:3]))
        except ValueError:
            raise ConfigError(
                f"unknown day in {spec!r}; use mon, tue, wed, thu, fri, sat, sun"
            ) from None
    if not days:
        raise ConfigError("no working days given")
    return days


def parse_time(value: str) -> dt.time:
    try:
        return dt.time.fromisoformat(value.strip())
    except ValueError:
        raise ConfigError(f"bad time {value!r}; use HH:MM, e.g. 08:00") from None


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        raise ConfigError(f"bad date {value!r}; use YYYY-MM-DD") from None


def _paths(value: str) -> list[str]:
    """Config values may list several paths, one per line or comma separated."""
    return [p.strip() for p in value.replace(",", "\n").splitlines() if p.strip()]


def find_config(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file {explicit} not found")
        return path
    env = os.environ.get("ATWORK_CONFIG")
    if env:
        return find_config(env)
    for candidate in DEFAULT_CONFIG_PATHS:
        path = candidate.expanduser()
        if path.is_file():
            return path
    return None


def load_config(path: Path) -> Settings:
    """Read an INI file with an [atwork] section. Relative paths in it are
    resolved against the config file's own directory."""
    parser = configparser.ConfigParser()
    try:
        with path.open(encoding="utf-8") as fh:
            parser.read_file(fh)
    except (OSError, configparser.Error) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from None
    if not parser.has_section("atwork"):
        raise ConfigError(f"config {path} has no [atwork] section")
    section = parser["atwork"]
    known = {"days", "start", "end", "ics", "holidays"}
    unknown = set(section) - known
    if unknown:
        raise ConfigError(f"config {path}: unknown setting(s) {', '.join(sorted(unknown))}")

    base = path.parent

    def resolve(p: str) -> str:
        q = Path(p).expanduser()
        return str(q if q.is_absolute() else base / q)

    s = Settings()
    if "days" in section:
        s.days = parse_days(section["days"])
    if "start" in section:
        s.start = parse_time(section["start"])
    if "end" in section:
        s.end = parse_time(section["end"])
    s.ics = [resolve(p) for p in _paths(section.get("ics", ""))]
    s.holidays = [resolve(p) for p in _paths(section.get("holidays", ""))]
    return s


# --------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------


def check(settings: Settings, now: dt.datetime, ignore_time: bool = False) -> tuple[bool, str]:
    """Return (at_work, reason)."""
    day = now.date()
    when = now.strftime("%a %Y-%m-%d %H:%M")

    if day.weekday() not in settings.days:
        return False, f"{when}: not a working day of the week"

    for path in settings.ics:
        if day in load_ics(path):
            return False, f"{when}: holiday (from {path})"
    for path in settings.holidays:
        if day in load_text(path):
            return False, f"{when}: holiday (from {path})"

    if not ignore_time:
        t = now.time()
        # start is inclusive, end exclusive: 08:00-17:00 means 08:00 to 16:59
        if not (settings.start <= t < settings.end):
            return False, (
                f"{when}: outside working hours "
                f"{settings.start:%H:%M}-{settings.end:%H:%M}"
            )

    return True, f"{when}: at work"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atwork",
        description=(
            "Exit 0 if it is working time, 1 if not, 2 on error. "
            "Use in cron as: atwork && your-command"
        ),
    )
    p.add_argument("--ics", action="append", default=[], metavar="FILE",
                   help="iCalendar file of holidays; all-day events count. Repeatable.")
    p.add_argument("--holidays", action="append", default=[], metavar="FILE",
                   help="text file of holiday dates or ranges. Repeatable.")
    p.add_argument("--days", metavar="SPEC",
                   help="working days, e.g. mon-fri (default) or mon,tue,thu")
    p.add_argument("--start", metavar="HH:MM", help="start of working day (default 08:00)")
    p.add_argument("--end", metavar="HH:MM",
                   help="end of working day, exclusive (default 17:00)")
    p.add_argument("--ignore-time", action="store_true",
                   help="only check the date, not the time of day")
    p.add_argument("--date", metavar="YYYY-MM-DD", help="check this date instead of today")
    p.add_argument("--time", metavar="HH:MM", help="check this time instead of now")
    p.add_argument("-c", "--config", metavar="FILE",
                   help="config file (default: $ATWORK_CONFIG, "
                        "~/.config/atwork/atwork.conf, then /etc/atwork.conf)")
    p.add_argument("--no-config", action="store_true", help="do not read any config file")
    p.add_argument("-v", "--verbose", action="store_true", help="print the reason")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings()
        if not args.no_config:
            path = find_config(args.config)
            if path:
                settings = load_config(path)

        # Command line options override (days/hours) or add to (files) the config.
        if args.days:
            settings.days = parse_days(args.days)
        if args.start:
            settings.start = parse_time(args.start)
        if args.end:
            settings.end = parse_time(args.end)
        settings.ics += args.ics
        settings.holidays += args.holidays
        if settings.start >= settings.end:
            raise ConfigError("start time must be before end time")

        now = dt.datetime.now()
        if args.date:
            now = dt.datetime.combine(parse_date(args.date), now.time())
        if args.time:
            now = dt.datetime.combine(now.date(), parse_time(args.time))

        at_work, reason = check(settings, now, ignore_time=args.ignore_time)
    except (ConfigError, HolidayFileError) as exc:
        print(f"atwork: error: {exc}", file=sys.stderr)
        return ERROR

    if args.verbose:
        print(reason)
    return AT_WORK if at_work else NOT_AT_WORK


if __name__ == "__main__":
    sys.exit(main())
