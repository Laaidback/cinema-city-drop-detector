from ccdrop.main import build_notifier, parse_args


def test_dry_run_defaults_to_false():
    assert parse_args([]).dry_run is False


def test_state_dir_has_default():
    assert parse_args([]).state_dir.name == "state"


def test_force_send_takes_match_value():
    assert parse_args(["--force-send", "Backrooms"]).force_send == "Backrooms"


def test_dry_run_needs_no_telegram_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert build_notifier(dry_run=True) is None
