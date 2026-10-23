from komora.mcp.client import _straight_apostrophes

TOOL = "silpo_find_products_batch"


def test_the_typographic_apostrophe_becomes_straight():
    got = _straight_apostrophes(TOOL, {"products": ["М’ясо мідій"]})
    assert got["products"] == ["М'ясо мідій"]


def test_every_lookalike_apostrophe_goes_the_same_way():
    odd = ["м’ясо", "мʼясо", "м‘ясо", "м´ясо"]
    got = _straight_apostrophes(TOOL, {"products": odd})
    assert got["products"] == ["м'ясо"] * 4


def test_a_query_that_is_already_straight_is_returned_untouched():
    args = {"products": ["Хліб Рум'янець", "молоко"]}
    assert _straight_apostrophes(TOOL, args) is args


def test_another_tool_is_not_touched():
    args = {"products": ["м’ясо"]}
    assert _straight_apostrophes("silpo_get_products", args) is args


def test_a_broken_field_does_not_raise():
    assert _straight_apostrophes(TOOL, {"products": None})["products"] is None
    assert _straight_apostrophes(TOOL, {}) == {}


def test_a_non_string_query_survives():
    args = {"products": ["м’ясо", 7]}
    assert _straight_apostrophes(TOOL, args)["products"] == ["м'ясо", 7]
