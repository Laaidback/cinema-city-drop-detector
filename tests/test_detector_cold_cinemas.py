from ccdrop.detector import cold_cinemas
from ccdrop.models import Config, WatchEntry, WatchState


def config_with(*entries, cinemas=("1090", "1064")):
    return Config(horizon_days=90, cinemas=cinemas, watch=entries)


def test_unknown_key_counts_as_cold():
    config = config_with(WatchEntry(match="A"))

    assert cold_cinemas(config, {}) == {"1090", "1064"}


def test_warm_pair_is_not_cold():
    config = config_with(WatchEntry(match="A"), cinemas=("1090",))
    state = {"A|1090": WatchState(warm=True)}

    assert cold_cinemas(config, state) == set()


def test_explicitly_cold_pair_is_cold():
    config = config_with(WatchEntry(match="A"), cinemas=("1090",))
    state = {"A|1090": WatchState(warm=False)}

    assert cold_cinemas(config, state) == {"1090"}


def test_entry_scoped_cinemas_limit_the_result():
    config = config_with(WatchEntry(match="A", cinemas=("1090",)))

    assert cold_cinemas(config, {}) == {"1090"}
