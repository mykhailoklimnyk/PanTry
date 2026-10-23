from komora.core.shortlist import cheapest, shortlist


def cut(names, mine=(), related=(), kin=None, cap=3, bought=None):
    return shortlist(
        names,
        own=lambda name: name in mine,
        bought=(lambda name: name in bought) if bought is not None else None,
        same_kind=(lambda name: name in kin) if kin is not None else None,
        related=lambda name: name in related,
        cap=cap,
    )


def test_the_guests_own_article_never_falls_off_the_ceiling():
    shelf = [f"чужий-{i}" for i in range(20)] + ["свій"]
    assert cut(shelf, mine={"свій"}, cap=3)[0] == "свій"


def test_related_beat_the_rest_but_lose_to_the_guests_own():
    shelf = ["сміття", "доречний", "свій"]
    assert cut(shelf, mine={"свій"}, related={"доречний"}) == [
        "свій",
        "доречний",
        "сміття",
    ]


def test_the_order_inside_a_tier_is_untouched():
    shelf = ["а", "б", "в", "г"]
    assert cut(shelf, related={"б", "в", "г"}, cap=4) == ["б", "в", "г", "а"]


def test_the_ceiling_counts_after_the_reordering_not_before():
    shelf = ["сміття1", "сміття2", "сміття3", "свій"]
    assert cut(shelf, mine={"свій"}, cap=1) == ["свій"]


def test_a_broken_ceiling_does_not_leave_the_agent_without_candidates():
    shelf = ["а", "б"]
    assert cut(shelf, cap=0) == ["а", "б"]
    assert cut(shelf, cap=-1) == ["а", "б"]


def test_a_short_shelf_is_not_padded_or_cut():
    assert cut(["а"], cap=10) == ["а"]
    assert cut([], cap=10) == []


def money(pairs, *, unit=None):
    return cheapest(pairs, unit_price=lambda item: item[1] if unit is None else unit(item))


def test_the_cheapest_is_counted_per_common_unit_not_per_price_tag():
    shelf = [("Томат черрі", 61.6), ("Гордій", 28.8), ("Ріана", 37.2)]
    assert money(shelf) == ("Гордій", 28.8)


def test_a_single_candidate_without_a_unit_stops_the_whole_comparison():
    assert money([("пачка", 12.0), ("штучний", None), ("ще", 3.0)]) is None


def test_nothing_to_choose_from_is_not_a_choice():
    assert money([]) is None


def test_a_free_candidate_is_a_broken_price_not_a_bargain():
    assert money([("дороге", 10.0), ("нуль", 0.0)]) is None


def test_a_tie_keeps_the_order_the_shop_gave():
    assert money([("перший", 5.0), ("другий", 5.0)]) == ("перший", 5.0)


def test_a_price_under_one_hryvnia_is_still_a_price():
    assert money([("дороге", 4.0), ("копійчане", 0.5)]) == ("копійчане", 0.5)


def test_the_same_node_beats_a_merely_related_name():
    shelf = ["рулет-рибний", "рулет-мясний"]
    assert cut(shelf, related=set(shelf), kin={"рулет-мясний"}) == [
        "рулет-мясний",
        "рулет-рибний",
    ]


def test_the_guests_own_article_still_outranks_its_own_node():
    shelf = ["той-вузол", "свій"]
    assert cut(shelf, mine={"свій"}, kin={"той-вузол"}) == ["свій", "той-вузол"]


def test_the_node_tier_does_not_remove_anything():
    shelf = ["а", "б", "в"]
    assert cut(shelf, kin=set(), cap=9) == shelf


def test_without_the_map_the_order_is_exactly_what_it_was_before():
    shelf = ["сміття", "доречний", "свій"]
    assert cut(shelf, mine={"свій"}, related={"доречний"}, kin=None) == cut(
        shelf, mine={"свій"}, related={"доречний"}
    )


def test_the_node_tier_survives_the_ceiling_and_the_rest_does_not():
    shelf = [f"чужий-{i}" for i in range(20)] + ["той-вузол"]
    assert cut(shelf, kin={"той-вузол"}, cap=2)[0] == "той-вузол"


def test_an_article_from_any_receipt_outranks_the_node_and_the_word():
    shelf = ["сміття", "доречний", "той вид", "з чеків", "свій"]
    assert cut(
        shelf,
        mine={"свій"},
        bought={"з чеків"},
        kin={"той вид"},
        related={"доречний"},
        cap=5,
    ) == ["свій", "з чеків", "той вид", "доречний", "сміття"]


def test_the_intents_own_article_still_goes_first():
    assert cut(["з чеків", "свій"], mine={"свій"}, bought={"з чеків", "свій"}, cap=2) == [
        "свій",
        "з чеків",
    ]


def test_without_the_receipts_axis_the_order_is_exactly_what_it_was():
    shelf = ["сміття", "доречний", "той вид"]
    assert cut(shelf, kin={"той вид"}, related={"доречний"}, cap=3) == [
        "той вид",
        "доречний",
        "сміття",
    ]
