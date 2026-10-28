# atwork

A script to check if it is currently a working day

Increasingly automated emails are sent by systems for staff at work. Email intrusiveness in staff leave time is an increasing problem interrupting work / life balance. This script is intended for use along side cron jobs to prevent emails being sent on what should be a holiday.

## How it works

`atwork` exits with:

| Exit code | Meaning |
|-----------|---------|
| `0` | It is working time |
| `1` | It is not working time (weekend, holiday, or outside hours) |
| `2` | Error (bad option, unreadable file, ...) |

In the shell, exit code 0 means "success", so you chain it with `&&` and the
command only runs at work:

```cron
# Send reminders every 15 minutes, but only during working time
*/15 * * * *  atwork && /usr/local/bin/send-reminders
```

Errors also exit non-zero, so a missing holiday file blocks the email rather
than letting it through. The error message goes to stderr, which cron will
normally email to you.

It is working time when **all** of these are true:

1. today is a working day of the week (default Monday to Friday);
2. today is not in any holiday `.ics` file or holidays text file;
3. the time is within working hours (default 08:00 up to, but not
   including, 17:00).

It uses the system's local time, so GMT/BST changes are handled for you.

## Installation

Requires Python 3.9 or later; there are no other dependencies.

```sh
pip install git+https://github.com/profcturner/atwork
# or, from a checkout
pip install .
```

You can also run it without installing: `python3 -m atwork` from the `src`
directory.

## Usage

```sh
atwork --ics ~/holidays/northern-ireland.ics --holidays ~/holidays/closures.txt && send-email
```

| Option | Description |
|--------|-------------|
| `--ics FILE` | iCalendar file of holidays. Every all-day event counts as a holiday; timed events are ignored. Repeatable. |
| `--holidays FILE` | Text file of holiday dates (see below). Repeatable. |
| `--days SPEC` | Working days, e.g. `mon-fri` (default), `mon,tue,thu`, `mon-thu,sat`. |
| `--start HH:MM` | Start of the working day (default `08:00`). |
| `--end HH:MM` | End of the working day, exclusive (default `17:00`). |
| `--ignore-time` | Only check the date, not the time of day. |
| `--date YYYY-MM-DD` | Check this date instead of today (for testing). |
| `--time HH:MM` | Check this time instead of now (for testing). |
| `-c, --config FILE` | Use this config file. |
| `--no-config` | Don't read any config file. |
| `-v, --verbose` | Print why it is or isn't working time. |

Testing your setup:

```sh
$ atwork --date 2026-12-25 --time 10:00 -v; echo $?
Fri 2026-12-25 10:00: holiday (from /home/me/holidays/northern-ireland.ics)
1
```

## UK bank holidays

gov.uk publishes official bank holiday calendars:

- England and Wales: <https://www.gov.uk/bank-holidays/england-and-wales.ics>
- Scotland: <https://www.gov.uk/bank-holidays/scotland.ics>
- Northern Ireland: <https://www.gov.uk/bank-holidays/northern-ireland.ics>

`atwork` only reads local files, so it never fails or delays because of the
network. Refresh the file now and then with a separate cron job, e.g. weekly:

```cron
0 3 * * 1  curl -sSf -o ~/holidays/northern-ireland.ics.new https://www.gov.uk/bank-holidays/northern-ireland.ics && mv ~/holidays/northern-ireland.ics.new ~/holidays/northern-ireland.ics
```

Downloading to a temporary name and then moving means a failed download never
leaves you with a broken file.

Any other `.ics` file works too, for example an export of a "University
closures" calendar. Recurring events (`RRULE`) are not expanded, so each
holiday needs to be its own event, as in the gov.uk feeds.

## Holidays text file

For days the bank holiday calendars don't cover, such as a Christmas closure
or local holidays:

```text
# Lines starting with # are comments; blank lines are ignored.

# A single day
2026-07-14

# An inclusive range
2026-12-24..2027-01-02

# Anything after the date is ignored, so you can label entries
2026-08-14  Staff development day
```

## Config file

To keep cron lines short, put your settings in a config file. `atwork` looks
for, in order:

1. the file given with `--config`;
2. the file named in the `ATWORK_CONFIG` environment variable;
3. `~/.config/atwork/atwork.conf`;
4. `/etc/atwork.conf`.

```ini
[atwork]
days = mon-fri
start = 08:00
end = 17:00

# Several files can be listed, one per line (indented) or comma separated.
# Relative paths are relative to this config file.
ics = northern-ireland.ics
      closures.ics
holidays = holidays.txt
```

Options given on the command line override `days`, `start` and `end` from the
config file, and add to its `ics` and `holidays` lists.

Then the cron line is just:

```cron
*/15 * * * *  atwork && /usr/local/bin/send-reminders
```

(If `atwork` was installed with `pip --user`, cron's limited `PATH` may not
include it; use the full path, e.g. `~/.local/bin/atwork`.)

## Development

```sh
pip install -e '.[test]'
pytest
```

## Licence

GPL-3.0; see [LICENSE](LICENSE).
