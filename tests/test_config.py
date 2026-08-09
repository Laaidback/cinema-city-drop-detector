import pytest

from ccdrop.config import load_config


def test_loads_horizon(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).horizon_days == 90


def test_unprefixed_cinema_id_gets_the_cinema_city_chain(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).cinemas == ("cc:1090",)


def test_prefixed_cinema_id_keeps_its_chain(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text('horizon_days: 90\ncinemas: ["cc:1090"]\nwatch:\n  - match: Backrooms\n')

    assert load_config(path).cinemas == ("cc:1090",)


def test_rejects_unknown_chain_prefix(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text('horizon_days: 90\ncinemas: ["kino:1090"]\nwatch:\n  - match: Backrooms\n')

    with pytest.raises(ValueError, match="kino:1090"):
        load_config(path)


def test_entry_cinema_id_gets_the_cinema_city_chain(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n    cinemas: [1090]\n"
    )

    assert load_config(path).watch[0].cinemas == ("cc:1090",)


def test_entry_cinemas_default_to_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).watch[0].cinemas is None


def test_entry_attributes_are_a_tuple(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n    attributes: [imax]\n"
    )

    assert load_config(path).watch[0].attributes == ("imax",)


def test_entry_attributes_default_to_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).watch[0].attributes is None


def test_empty_attributes_list_becomes_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n    attributes: []\n"
    )

    assert load_config(path).watch[0].attributes is None


def test_entry_notifies_by_default(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).watch[0].notify is True


def test_entry_notify_false_is_parsed(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n    notify: false\n"
    )

    assert load_config(path).watch[0].notify is False


def test_rejects_non_boolean_notify(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n    notify: tak\n"
    )

    with pytest.raises(ValueError, match="notify"):
        load_config(path)


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


def with_schedule(tmp_path, body):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\nschedule:\n" + body
    )
    return path


def test_absent_schedule_becomes_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).schedule is None


def test_schedule_hours_are_a_tuple(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  before: 2\n  after: 3\n")

    assert load_config(path).schedule.hours == (8, 22)


def test_schedule_before_is_parsed(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  before: 2\n  after: 3\n")

    assert load_config(path).schedule.before == 2


def test_schedule_after_is_parsed(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  before: 2\n  after: 3\n")

    assert load_config(path).schedule.after == 3


def test_schedule_before_defaults_to_zero(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n")

    assert load_config(path).schedule.before == 0


def test_schedule_after_defaults_to_zero(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n")

    assert load_config(path).schedule.after == 0


def test_rejects_schedule_without_hours(tmp_path):
    path = with_schedule(tmp_path, "  before: 2\n  after: 3\n")

    with pytest.raises(ValueError, match="hours"):
        load_config(path)


def test_rejects_single_hour(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8]\n")

    with pytest.raises(ValueError, match="hours"):
        load_config(path)


def test_rejects_hour_outside_the_clock(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 24]\n")

    with pytest.raises(ValueError, match="0-23"):
        load_config(path)


def test_rejects_reversed_hours(tmp_path):
    path = with_schedule(tmp_path, "  hours: [22, 8]\n")

    with pytest.raises(ValueError, match="hours"):
        load_config(path)


def test_rejects_negative_before(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  before: -1\n")

    with pytest.raises(ValueError, match="before"):
        load_config(path)


def test_rejects_negative_after(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  after: -1\n")

    with pytest.raises(ValueError, match="after"):
        load_config(path)


def test_rejects_margins_that_make_windows_overlap(tmp_path):
    path = with_schedule(tmp_path, "  hours: [8, 22]\n  before: 30\n  after: 29\n")

    with pytest.raises(ValueError, match="59"):
        load_config(path)
