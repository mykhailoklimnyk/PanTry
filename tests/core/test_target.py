from decimal import Decimal

from komora.core.target import (
    LAYER_WIDTH,
    OVERSHOOT_OPTIONS,
    SUPPLY_RANK,
    Candidate,
    band,
    fill,
    next_cut,
    overshoot,
    priced,
    reach,
    spare_cut,
    supply_rank,
)


def money(value: str) -> Decimal:
    return Decimal(value)


def test_the_band_is_ten_percent_on_both_sides():
    edges = band(money("3000"))

    assert edges.low == money("2700.00")
    assert edges.high == money("3300.00")
    assert edges.holds(money("2772"))
    assert not edges.holds(money("1100")), "живий кейс, з якого почалась задача"


def test_what_is_missing_is_counted_to_the_LOW_edge():
    edges = band(money("3000"))

    assert edges.short_by(money("1227")) == money("1473.00")
    assert edges.short_by(money("2800")) == 0


def test_a_basket_inside_the_band_is_still_topped_up_to_the_top():
    edges = band(money("1000"))
    pool = [Candidate(key="a", rank=100, cost=money("50"), why="")]

    filled = fill(have=money("950"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["a"] and spent == money("50")


def test_a_basket_already_at_the_top_is_not_topped_up():
    edges = band(money("1000"))
    pool = [Candidate(key="a", rank=100, cost=money("50"), why="")]

    assert fill(have=money("1100"), band=edges, pool=pool).taken == ()


def test_the_strongest_reason_goes_first():
    edges = band(money("1000"))
    pool = [
        Candidate(key="запас", rank=300, cost=money("200"), why="запас"),
        Candidate(key="скоро", rank=102, cost=money("200"), why="закінчиться за 2 дн"),
        Candidate(key="мовчить", rank=200, cost=money("200"), why="мовчить"),
    ]

    filled = fill(have=money("400"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["скоро", "мовчить", "запас"]
    assert spent == money("600")


def test_a_pool_too_thin_for_the_band_stops_where_it_ends():
    edges = band(money("3000"))
    pool = [Candidate(key=str(i), rank=100 + i, cost=money("100"), why="") for i in range(5)]

    filled = fill(have=money("1227"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert len(taken) == 5 and spent == money("500")
    assert not edges.holds(money("1227") + spent), "1727 нижче за 2700 — і це видно"


def test_the_upper_edge_is_never_crossed():
    edges = band(money("1000"))
    pool = [
        Candidate(key="велике", rank=100, cost=money("900"), why=""),
        Candidate(key="мале", rank=200, cost=money("100"), why=""),
    ]

    filled = fill(have=money("500"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["мале"], "900 понад 500 дало б 1400 при стелі 1100"
    assert spent == money("100")


def test_a_candidate_without_a_price_is_not_taken():
    edges = band(money("1000"))
    pool = [
        Candidate(key="без ціни", rank=100, cost=None, why=""),
        Candidate(key="з ціною", rank=200, cost=money("300"), why=""),
    ]

    taken = fill(have=money("500"), band=edges, pool=pool).taken

    assert [c.key for c in taken] == ["з ціною"]


def test_the_band_names_itself_with_numbers():
    assert band(money("3000")).phrase() == "ціль 3000 грн, коридор 2700-3300"


def test_a_basket_exactly_on_the_top_edge_is_already_full():
    edges = band(money("1000"))
    pool = [Candidate(key="зайве", rank=100, cost=money("50"), why="")]

    assert fill(have=money("1100"), band=edges, pool=pool).taken == ()


def test_a_free_candidate_is_not_taken():
    edges = band(money("1000"))
    pool = [
        Candidate(key="нуль", rank=100, cost=money("0"), why=""),
        Candidate(key="справжнє", rank=200, cost=money("300"), why=""),
    ]

    filled = fill(have=money("500"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["справжнє"] and spent == money("300")


def test_the_running_total_grows_and_stops_the_fill():
    edges = band(money("1000"))
    pool = [Candidate(key=f"{i:02d}", rank=100 + i, cost=money("200"), why="") for i in range(10)]

    filled = fill(have=money("0"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert len(taken) == 5, "п'ять по 200 закривають нижню межу 900"
    assert spent == money("1000")


def test_the_fill_stops_at_the_top_edge_and_not_a_row_later():
    edges = band(money("1000"))
    pool = [Candidate(key=f"{i:02d}", rank=100 + i, cost=money("100"), why="") for i in range(12)]

    filled = fill(have=money("0"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert len(taken) == 11 and spent == money("1100")


def test_the_upper_edge_holds_when_something_is_already_taken():
    edges = band(money("1000"))
    pool = [
        Candidate(key="a", rank=100, cost=money("600"), why=""),
        Candidate(key="b", rank=200, cost=money("600"), why=""),
    ]

    filled = fill(have=money("0"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["a"] and spent == money("600")


def test_a_one_hryvnia_candidate_is_still_a_candidate():
    edges = band(money("1000"))
    pool = [Candidate(key="дешеве", rank=100, cost=money("1"), why="")]

    taken = fill(have=money("899"), band=edges, pool=pool).taken

    assert [c.key for c in taken] == ["дешеве"]


def test_a_candidate_that_lands_exactly_on_the_upper_edge_is_taken():
    edges = band(money("1000"))
    pool = [Candidate(key="рівно", rank=100, cost=money("1100"), why="")]

    filled = fill(have=money("0"), band=edges, pool=pool)

    taken, spent = filled.taken, filled.spent

    assert [c.key for c in taken] == ["рівно"] and spent == money("1100")


def test_the_fill_does_not_stack_the_same_kind():
    edges = band(Decimal(2300))
    pool = [
        Candidate(key="Томат Гордій Черрі", rank=200, cost=Decimal(72), why="", kind="Томат"),
        Candidate(key="Томат Есміра рожевий", rank=300, cost=Decimal(80), why="", kind="Томат"),
        Candidate(key="Хліб Рум'янець", rank=400, cost=Decimal(57), why="", kind="Хліб"),
    ]

    picked = fill(have=Decimal(1900), band=edges, pool=pool).taken

    assert [item.key for item in picked] == ["Томат Гордій Черрі", "Хліб Рум'янець"]


def test_a_kind_already_in_the_basket_is_not_filled_again():
    edges = band(Decimal(2300))
    pool = [Candidate(key="Томат Есміра", rank=100, cost=Decimal(80), why="", kind="Томат")]

    filled = fill(have=Decimal(2000), band=edges, pool=pool, covered={"Томат"})

    picked, spent = filled.taken, filled.spent

    assert picked == () and spent == 0


def test_a_candidate_without_a_kind_argues_with_nobody():
    edges = band(Decimal(2300))
    pool = [
        Candidate(key="перше", rank=100, cost=Decimal(40), why=""),
        Candidate(key="друге", rank=200, cost=Decimal(40), why=""),
    ]

    picked = fill(have=Decimal(1900), band=edges, pool=pool, covered={""}).taken

    assert [item.key for item in picked] == ["перше", "друге"]


def test_a_shortfall_says_which_candidates_it_could_not_use():
    edges = band(money("1000"))
    pool = [
        Candidate(key="без ціни", rank=100, cost=None, why=""),
        Candidate(key="той самий вид", rank=200, cost=money("50"), why="", kind="томат"),
        Candidate(key="взятий", rank=300, cost=money("50"), why="", kind="хліб"),
    ]

    filled = fill(have=money("100"), band=edges, pool=pool, covered={"томат"})

    assert [c.key for c in filled.taken] == ["взятий"]
    assert filled.no_price == 1
    assert filled.same_kind == 1
    assert filled.over_high == 0
    assert filled.note() == "1 без ціни в чеках, 1 того ж виду, що вже в кошику"


def test_a_candidate_that_does_not_fit_the_top_is_counted_separately():
    edges = band(money("1000"))
    pool = [Candidate(key="дорогий", rank=100, cost=money("900"), why="", kind="сир")]

    filled = fill(have=money("900"), band=edges, pool=pool)

    assert filled.taken == () and filled.over_high == 1
    assert filled.note() == "1 не влізли під верхню межу"


def test_a_full_basket_says_nothing_about_the_pool():
    edges = band(money("1000"))
    pool = [Candidate(key="а", rank=100, cost=None, why="")]

    assert fill(have=money("1200"), band=edges, pool=pool).note() == ""


def test_an_empty_pool_has_no_sum_at_all():
    got = reach([])

    assert got.kinds == 0
    assert got.estimate is None


def test_only_priced_kinds_are_counted_and_summed():
    pool = [
        Candidate(key="без ціни", rank=100, cost=None, why=""),
        Candidate(key="нуль", rank=200, cost=money("0"), why=""),
        Candidate(key="мінус", rank=300, cost=money("-5"), why=""),
        Candidate(key="хліб", rank=400, cost=money("40.50"), why=""),
        Candidate(key="молоко", rank=500, cost=money("59.50"), why=""),
    ]

    got = reach(pool)

    assert got.kinds == 2
    assert got.estimate == money("100.00")


def test_the_pool_the_chip_shows_is_the_pool_the_fill_takes_from():
    pool = [
        Candidate(key="без ціни", rank=100, cost=None, why="", kind="сир"),
        Candidate(key="хліб", rank=200, cost=money("40"), why="", kind="хліб"),
        Candidate(key="молоко", rank=300, cost=money("60"), why="", kind="молоко"),
    ]

    got = reach(pool)
    filled = fill(have=money("0"), band=band(money("100")), pool=pool)

    assert got.kinds == 2 and got.estimate == money("100")
    assert [c.key for c in filled.taken] == ["хліб", "молоко"]
    assert filled.no_price == 1


def test_priced_says_the_cost_and_not_just_yes_or_no():
    assert priced(Candidate(key="a", rank=1, cost=money("12.30"), why="")) == money("12.30")
    assert priced(Candidate(key="b", rank=1, cost=money("0"), why="")) is None
    assert priced(Candidate(key="c", rank=1, cost=None, why="")) is None


def _queue(*prices: str) -> list[tuple[str, Decimal]]:
    return [(f"намір {n}", money(price)) for n, price in enumerate(prices)]


def test_the_queue_head_is_taken_while_it_does_not_break_the_floor():
    step = next_cut(money("2000"), limit=money("1700"), low=money("1530"), queue=_queue("200", "5"))

    assert step is not None
    assert step.index == 0 and step.skipped == () and step.saves


def test_a_candidate_that_would_drop_the_basket_under_the_floor_waits():
    step = next_cut(
        money("1701.50"), limit=money("1700"), low=money("1530"), queue=_queue("249.90", "1.50")
    )

    assert step is not None
    assert step.index == 1, "зависокий кандидат чекає, а не знімається"
    assert step.skipped == ("намір 0",), "пропущений називається вголос"
    assert step.saves


def test_when_nobody_saves_the_floor_the_head_goes_as_before():
    step = next_cut(
        money("1701.50"), limit=money("1700"), low=money("1530"), queue=_queue("300", "400")
    )

    assert step is not None
    assert step.index == 0 and not step.saves
    assert step.skipped == (), "голову беремо не пропустивши нікого, а за браком кращого"


def test_a_basket_inside_the_limit_is_not_cut_at_all():
    assert (
        next_cut(money("1700"), limit=money("1700"), low=money("1530"), queue=_queue("5")) is None
    )
    assert next_cut(money("2000"), limit=money("1700"), low=money("1530"), queue=[]) is None


def test_our_own_fill_gives_up_the_cheapest_row_that_is_enough():
    step = spare_cut(money("3400"), limit=money("3300"), rows=_queue("900", "150"))

    assert step is not None
    assert step.index == 1 and step.saves


def test_our_own_fill_gives_up_the_dearest_row_when_none_is_enough():
    step = spare_cut(money("3400"), limit=money("3000"), rows=_queue("120", "300", "150"))

    assert step is not None
    assert step.index == 1 and not step.saves


def test_our_own_fill_is_not_touched_under_the_limit():
    assert spare_cut(money("3000"), limit=money("3300"), rows=_queue("900")) is None
    assert spare_cut(money("3400"), limit=money("3300"), rows=[]) is None


def _rows(*prices: str) -> list[tuple[str, str, Decimal]]:
    return [(f"намір {n}", f"Товар {n}", money(price)) for n, price in enumerate(prices)]


def test_only_the_rows_that_actually_save_become_options():
    ways = overshoot(money("2220"), limit=money("1760"), rows=_rows("520", "129"))

    assert [drop.name for drop in ways.drops] == ["Товар 0"], "129 грн перебору не закриває"
    assert ways.drops[0].left == money("1700")
    assert ways.asks()


def test_the_dearest_row_stands_first():
    ways = overshoot(money("2220"), limit=money("1760"), rows=_rows("520", "980", "700"))

    assert [drop.price for drop in ways.drops] == [money("980"), money("700"), money("520")]


def test_the_number_of_options_has_a_ceiling():
    ways = overshoot(
        money("2220"), limit=money("1760"), rows=_rows("520", "530", "540", "550", "560")
    )

    assert len(ways.drops) == OVERSHOOT_OPTIONS


def test_without_a_single_saving_row_there_is_nothing_to_ask():
    ways = overshoot(money("2220"), limit=money("1760"), rows=_rows("20", "30"))

    assert not ways.asks() and ways.drops == ()
    assert ways.target == money("2300")


def test_the_raised_target_is_the_smallest_round_one_that_holds_the_basket():
    ways = overshoot(money("2220.04"), limit=money("1760"), rows=_rows("999"))

    assert ways.target == money("2300")
    assert ways.target >= money("2220.04"), "різ спиняється на самій цілі, отже вона вміщає кошик"


def test_a_basket_exactly_at_the_top_edge_is_not_over_it():
    ways = overshoot(money("1760"), limit=money("1760"), rows=_rows("10"))

    assert ways.drops and ways.drops[0].price == money("10"), "нуль перебору проходить кожен рядок"


def test_the_options_are_measured_from_the_cut_limit_not_from_the_corridor():
    edges = band(money("3500"))
    assert edges.high == money("3850.00"), "коридор справді ВИЩИЙ за кошик"

    ways = overshoot(money("3787"), limit=money("3500"), rows=_rows("300", "200"))

    assert [drop.price for drop in ways.drops] == [money("300")], "200 грн перебору не закриває"
    assert ways.drops[0].left <= money("3500"), "варіант мусить вертати кошик під межу"


def test_the_raised_target_covers_the_basket_itself():
    ways = overshoot(money("3787"), limit=money("3500"), rows=_rows("300"))

    assert ways.target == money("3800") and ways.target >= money("3787")


def test_the_supply_rank_stays_inside_its_layer():
    assert supply_rank(210) == SUPPLY_RANK + LAYER_WIDTH - 1
    assert supply_rank(210) < 500, "покинуте (500) стоїть за всіма, а не поперед"
    assert supply_rank(0) == SUPPLY_RANK


def test_days_and_not_the_share_separate_the_cat_food_from_the_milk():
    assert supply_rank(3) < supply_rank(90)


def test_the_unknown_number_of_days_goes_to_the_TAIL_and_not_to_the_head():
    assert supply_rank(None) > supply_rank(0)
    assert supply_rank(None) == supply_rank(1000), "хвіст ярусу, а не позаду нього"


def test_a_kind_that_is_already_overdue_gets_the_head_of_the_layer():
    assert supply_rank(-30) == SUPPLY_RANK


def test_the_agent_may_raise_the_limit_for_an_occasion_but_not_above_the_stretch():
    from komora.core.target import STRETCH, stretch

    taken = stretch(Decimal(1600), Decimal("3000"), why="гості на шістьох")
    assert taken is not None and taken.refused is None
    assert taken.target == Decimal(3000) and taken.named == Decimal(1600)

    too_much = stretch(Decimal(1600), Decimal(1600) * STRETCH + 1)
    assert too_much is not None and too_much.refused is not None
    assert too_much.target == Decimal(1600), "відкинута пропозиція лишає названу межу"


def test_the_guest_word_is_older_than_the_agent_and_the_agent_may_not_lower():
    from komora.core.target import stretch

    said = stretch(Decimal(1600), Decimal(3000), said=True)
    assert said is not None and said.refused and said.target == Decimal(1600)

    lower = stretch(Decimal(3000), Decimal(1600))
    assert lower is not None and lower.refused and lower.target == Decimal(3000)

    assert stretch(Decimal(1600), None) is None
    assert stretch(Decimal(1600), Decimal("1600.4")) is None, "та сама межа -- не пропозиція"
