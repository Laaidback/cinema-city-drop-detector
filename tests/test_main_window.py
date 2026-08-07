import dataclasses
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ccdrop import main as main_module

WARSAW = ZoneInfo("Europe/Warsaw")
WATCHED = "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n"
SCHEDULED = WATCHED + "schedule:\n  hours: [8, 22]\n  before: 2\n  after: 3\n"


@dataclasses.dataclass
class Run:
    code: int
    cycles: list
    clients: list
    state_dir: Path


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    cycles = []
    clients = []

    def fake_run_cycle(config, state, api, notifier, today, now, dry_run=False, force_match=None):
        cycles.append(now)
        return state

    monkeypatch.setattr(main_module, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(main_module, "ApiClient", lambda *args, **kwargs: clients.append("client"))

    def go(yaml_text, hour, minute, argv=()):
        config = tmp_path / "c.yaml"
        config.write_text(yaml_text)
        state_dir = tmp_path / "state"
        monkeypatch.setattr(
            main_module,
            "current_time",
            lambda: datetime(2026, 8, 3, hour, minute, tzinfo=WARSAW),
        )
        code = main_module.main(["--config", str(config), "--state-dir", str(state_dir), *argv])
        return Run(code=code, cycles=cycles, clients=clients, state_dir=state_dir)

    return go


def test_outside_the_window_exits_zero(run):
    assert run(SCHEDULED, 9, 30).code == 0


def test_outside_the_window_skips_the_cycle(run):
    assert run(SCHEDULED, 9, 30).cycles == []


def test_outside_the_window_builds_no_api_client(run):
    assert run(SCHEDULED, 9, 30).clients == []


def test_outside_the_window_writes_no_state_file(run):
    result = run(SCHEDULED, 9, 30)

    assert not (result.state_dir / "seen.json").exists()


def test_outside_the_window_logs_one_line(run, caplog):
    caplog.set_level(logging.INFO, logger="ccdrop")
    run(SCHEDULED, 9, 30)

    assert len([r for r in caplog.records if r.name == "ccdrop"]) == 1


def test_inside_the_window_runs_the_cycle(run):
    assert len(run(SCHEDULED, 8, 59).cycles) == 1


def test_dry_run_outside_the_window_skips_the_cycle(run):
    assert run(SCHEDULED, 9, 30, ["--dry-run"]).cycles == []


def test_absent_schedule_runs_outside_the_hours(run):
    assert len(run(WATCHED, 3, 30).cycles) == 1
