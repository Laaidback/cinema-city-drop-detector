import pytest

from ccdrop.config import load_config


def test_loads_horizon(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).horizon_days == 90


def test_cinema_ids_are_strings(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).cinemas == ("1090",)


def test_entry_cinemas_default_to_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).watch[0].cinemas is None


def test_rejects_empty_watch(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch: []\n")

    with pytest.raises(ValueError, match="watch"):
        load_config(path)


def test_rejects_entry_cinema_outside_global_list(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: X\n    cinemas: [9999]\n"
    )

    with pytest.raises(ValueError, match="9999"):
        load_config(path)
