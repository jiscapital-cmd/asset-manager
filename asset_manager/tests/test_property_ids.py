from asset_manager.property_ids import resolve_property_id

KNOWN = ["champions_pointe", "memorial_apartments", "garfield_vista", "madgrey_apartments"]


def test_resolve_property_id_returns_exact_match_unchanged():
    assert resolve_property_id("champions_pointe", KNOWN) == "champions_pointe"


def test_resolve_property_id_resolves_hyphenated_variant():
    assert resolve_property_id("champions-pointe", KNOWN) == "champions_pointe"


def test_resolve_property_id_resolves_title_case_with_space():
    assert resolve_property_id("Champions Pointe", KNOWN) == "champions_pointe"


def test_resolve_property_id_resolves_no_separator_variant():
    assert resolve_property_id("championspointe", KNOWN) == "champions_pointe"


def test_resolve_property_id_returns_raw_when_no_match_found():
    assert resolve_property_id("some-other-property", KNOWN) == "some-other-property"


def test_resolve_property_id_returns_raw_when_known_list_empty():
    assert resolve_property_id("champions-pointe", []) == "champions-pointe"
