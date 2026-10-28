import subprocess
import sys
from pathlib import Path

import pytest

from atwork.cli import AT_WORK, ERROR, NOT_AT_WORK, main, parse_days

DATA = Path(__file__).parent / "data"
ICS = str(DATA / "bank-holidays.ics")


def run(*args):
    return main(["--no-config", *args])


# 2026-10-28 is a Wednesday, 2026-10-31 a Saturday.

def test_working_hours():
    assert run("--date", "2026-10-28", "--time", "10:00") == AT_WORK


def test_before_and_after_hours():
    assert run("--date", "2026-10-28", "--time", "07:59") == NOT_AT_WORK
    assert run("--date", "2026-10-28", "--time", "08:00") == AT_WORK
    assert run("--date", "2026-10-28", "--time", "16:59") == AT_WORK
    assert run("--date", "2026-10-28", "--time", "17:00") == NOT_AT_WORK


def test_weekend():
    assert run("--date", "2026-10-31", "--time", "10:00") == NOT_AT_WORK


def test_custom_days_and_hours():
    assert run("--date", "2026-10-31", "--time", "10:00", "--days", "mon-sat") == AT_WORK
    assert run("--date", "2026-10-28", "--time", "18:00", "--end", "19:00") == AT_WORK
    assert run("--date", "2026-10-28", "--time", "10:00", "--days", "mon,tue") == NOT_AT_WORK


def test_ignore_time():
    assert run("--date", "2026-10-28", "--time", "23:00", "--ignore-time") == AT_WORK


def test_ics_holiday():
    assert run("--ics", ICS, "--date", "2026-12-25", "--time", "10:00") == NOT_AT_WORK
    assert run("--ics", ICS, "--date", "2026-12-24", "--time", "10:00") == AT_WORK


def test_text_holiday(tmp_path):
    h = tmp_path / "holidays.txt"
    h.write_text("2026-12-21..2026-12-24\n")
    assert run("--holidays", str(h), "--date", "2026-12-22", "--time", "10:00") == NOT_AT_WORK
    assert run("--holidays", str(h), "--date", "2026-12-18", "--time", "10:00") == AT_WORK


def test_errors_exit_2(tmp_path, capsys):
    assert run("--ics", str(tmp_path / "missing.ics")) == ERROR
    assert "cannot read" in capsys.readouterr().err
    assert run("--start", "nine") == ERROR
    assert run("--start", "18:00") == ERROR  # after default end
    assert run("--days", "funday") == ERROR


def test_verbose(capsys):
    run("--ics", ICS, "--date", "2026-12-25", "--time", "10:00", "-v")
    assert "holiday" in capsys.readouterr().out


def test_config_file(tmp_path):
    (tmp_path / "hol.txt").write_text("2026-11-02\n")
    conf = tmp_path / "atwork.conf"
    conf.write_text(
        "[atwork]\n"
        "days = mon-thu\n"
        "start = 09:00\n"
        "end = 17:30\n"
        f"ics = {ICS}\n"
        "holidays = hol.txt\n"  # relative to the config file
    )
    c = ["--config", str(conf)]
    assert main([*c, "--date", "2026-10-28", "--time", "17:15"]) == AT_WORK
    assert main([*c, "--date", "2026-10-28", "--time", "08:30"]) == NOT_AT_WORK
    assert main([*c, "--date", "2026-10-30", "--time", "10:00"]) == NOT_AT_WORK  # Friday
    assert main([*c, "--date", "2026-11-02", "--time", "10:00"]) == NOT_AT_WORK
    assert main([*c, "--date", "2026-12-25", "--time", "10:00"]) == NOT_AT_WORK


def test_config_unknown_key(tmp_path):
    conf = tmp_path / "atwork.conf"
    conf.write_text("[atwork]\nstrat = 09:00\n")
    assert main(["--config", str(conf)]) == ERROR


def test_env_config(tmp_path, monkeypatch):
    conf = tmp_path / "atwork.conf"
    conf.write_text("[atwork]\ndays = sat\n")
    monkeypatch.setenv("ATWORK_CONFIG", str(conf))
    assert main(["--date", "2026-10-31", "--time", "10:00"]) == AT_WORK


@pytest.mark.parametrize("spec,expected", [
    ("mon-fri", {0, 1, 2, 3, 4}),
    ("Mon,Wed,Fri", {0, 2, 4}),
    ("monday-wednesday,sat", {0, 1, 2, 5}),
])
def test_parse_days(spec, expected):
    assert parse_days(spec) == expected


def test_shell_chaining():
    """The whole point: `atwork && cmd` runs cmd only at work."""
    base = [sys.executable, "-m", "atwork", "--no-config", "--ics", ICS, "--time", "10:00"]
    env = {"PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    work = subprocess.run([*base, "--date", "2026-12-24"], env=env)
    xmas = subprocess.run([*base, "--date", "2026-12-25"], env=env)
    assert work.returncode == 0
    assert xmas.returncode == 1
