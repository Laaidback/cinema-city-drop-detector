from ccdrop.main import parse_args


def test_dry_run_defaults_to_false():
    assert parse_args([]).dry_run is False


def test_state_dir_has_default():
    assert parse_args([]).state_dir.name == "state"


def test_force_send_takes_match_value():
    assert parse_args(["--force-send", "Backrooms"]).force_send == "Backrooms"
