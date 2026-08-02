from ccdrop.matching import matches


def test_phrase_matches_substring():
    assert matches("Backrooms", "Backrooms. Bez wyjścia")


def test_phrase_ignores_case():
    assert matches("backrooms", "Backrooms. Bez wyjścia")


def test_phrase_ignores_diacritics():
    assert matches("Zolw", "Żółw w wielkim mieście")


def test_phrase_rejects_unrelated_title():
    assert not matches("Backrooms", "Diuna 3")


def test_regex_mode_anchors():
    assert matches("/^Diuna.*3$/", "Diuna część 3")


def test_regex_mode_respects_anchors():
    assert not matches("/^Diuna.*3$/", "Nowa Diuna 3 IMAX")


def test_regex_mode_keeps_diacritics():
    assert matches("/Żółw/", "Żółw w wielkim mieście")
