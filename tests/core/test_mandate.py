from decimal import Decimal

from komora.core.mandate import (
    build_comment,
    chain_phrase,
    empty_chain_phrase,
    price_fork,
    price_fork_comment,
)
from komora.core.substitution import Alternative, Source


def alt(name: str, price: str = "10") -> Alternative:
    return Alternative(
        external_product_id=name,
        name=name,
        source=Source.HISTORY,
        price=Decimal(price),
    )


def test_chain_reads_as_an_instruction_to_a_human():
    phrase = chain_phrase([alt("Сир Джюгас"), alt("Пармезан"), alt("Грана Падано")])
    assert phrase == "якщо немає — Сир Джюгас, потім Пармезан, потім Грана Падано, інакше не брати"


def test_single_alternative_has_no_dangling_conjunction():
    assert chain_phrase([alt("Пармезан")]) == "якщо немає — Пармезан, інакше не брати"


def test_empty_chain_returns_none_not_a_phrase():
    assert chain_phrase([]) is None


def test_empty_chain_is_still_said_out_loud():
    mandate = build_comment(chain=[])
    assert mandate.comment == empty_chain_phrase()
    assert "не брати" in mandate.comment


def test_shelf_life_follows_the_chain():
    mandate = build_comment(
        chain=[alt("Пармезан")],
        shelf_life="термін придатності не менше ніж до 19.08",
    )
    assert mandate.comment == (
        "якщо немає — Пармезан, інакше не брати; термін придатності не менше ніж до 19.08"
    )
    assert mandate.dropped == ()


def test_wishes_go_last():
    mandate = build_comment(
        chain=[alt("Банани")],
        shelf_life="термін до 19.08",
        wishes="не дуже стиглі",
    )
    assert mandate.comment.endswith("не дуже стиглі")


def test_wishes_are_dropped_first_when_the_field_is_tight():
    mandate = build_comment(
        chain=[alt("Пармезан")],
        shelf_life="термін до 19.08",
        wishes="не дуже стиглі",
        max_length=60,
    )
    assert "не дуже стиглі" not in mandate.comment
    assert "не дуже стиглі" in mandate.dropped
    assert len(mandate.comment) <= 60


def test_chain_is_shortened_only_after_everything_else_is_gone():
    mandate = build_comment(
        chain=[alt("Сир Джюгас"), alt("Пармезан"), alt("Грана Падано")],
        shelf_life="термін до 19.08",
        max_length=50,
    )

    assert len(mandate.comment) <= 50
    assert "Сир Джюгас" in mandate.comment
    assert "Грана Падано" in mandate.dropped


def test_everything_dropped_is_reported_not_swallowed():
    mandate = build_comment(
        chain=[alt("А"), alt("Б")],
        shelf_life="термін до 19.08",
        wishes="нарізати",
        max_length=40,
    )
    assert mandate.dropped
    assert len(mandate.comment) <= 40


def test_comment_never_exceeds_the_limit_even_with_one_long_name():
    mandate = build_comment(chain=[alt("Х" * 400)], max_length=100)
    assert len(mandate.comment) <= 100


def test_price_fork_rounds_outward():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    comment = price_fork_comment(price_fork(Decimal("54.90")))
    assert "49,41–60,39 грн" in comment
    assert "інакше не брати" in comment


def test_the_axis_of_the_swap_is_named_by_the_agent():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    named = price_fork_comment(
        price_fork(Decimal("57.21")), kind="інший цільнозерновий пшеничний, 400 г"
    )
    assert "інший цільнозерновий пшеничний, 400 г" in named
    assert "51,48–62,94 грн" in named, "вилку рахує КОД і приклеює до тексту агента"
    assert "марки" not in named


def test_without_the_agent_the_fallback_names_no_axis_at_all():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    assert "того самого виду" in price_fork_comment(price_fork(Decimal("57.21")))
    assert "марки" not in price_fork_comment(price_fork(Decimal("57.21")))
    assert "того самого виду" in price_fork_comment(price_fork(Decimal("57.21")), kind="   ")


def test_an_axis_that_does_not_fit_the_field_is_dropped_whole():
    from decimal import Decimal

    from komora.core.mandate import MAX_COMMENT_LENGTH, price_fork, price_fork_comment

    comment = price_fork_comment(price_fork(Decimal(100)), kind="дуже довга вісь " * 40)
    assert len(comment) <= MAX_COMMENT_LENGTH
    assert "дуже довга вісь" not in comment
    assert "того самого виду" in comment


def test_price_fork_respects_percent():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    comment = price_fork_comment(price_fork(Decimal(100), percent=20))
    assert "80–120 грн" in comment


def test_the_fork_stops_at_a_sum_when_the_percent_stops_limiting():
    from decimal import Decimal

    from komora.core.mandate import FORK_CAP, price_fork

    dear = price_fork(Decimal(1599))

    assert (dear.low, dear.high) == (Decimal(1549), Decimal(1649))
    assert dear.high - Decimal(1599) == FORK_CAP
    assert price_fork(Decimal("34.90")).phrase == "у межах 31,41–38,39 грн"


def test_the_fork_never_promises_wider_than_the_percent_it_names():
    from decimal import Decimal

    from komora.core.mandate import FORK_STEP, price_fork

    for price in (
        Decimal("0.90"),
        Decimal("5.49"),
        Decimal("9.50"),
        Decimal("19.99"),
        Decimal("245"),
        Decimal("719"),
    ):
        fork = price_fork(price)
        assert fork.low > 0, f"{price}: низ вилки нулем не буває -- це дозвіл на будь-що"
        assert fork.low >= price * Decimal("0.9") - FORK_STEP, f"{price}: низ нижче обіцяного"
        assert fork.high <= price * Decimal("1.1") + FORK_STEP, f"{price}: верх вище обіцяного"


def test_the_cheapest_line_still_gets_a_fork_that_means_something():
    from decimal import Decimal

    from komora.core.mandate import price_fork

    assert price_fork(Decimal("0.90")).phrase == "у межах 0,81–0,99 грн"


def test_the_fork_prints_whole_hryvnias_without_a_tail_of_zeros():
    from decimal import Decimal

    from komora.core.mandate import money

    assert money(Decimal("647.00")) == "647"
    assert money(Decimal("64.79")) == "64,79"
    assert money(Decimal("56.70")) == "56,7"


def test_price_fork_rejects_nonsense():
    from decimal import Decimal

    import pytest

    from komora.core.mandate import price_fork

    with pytest.raises(ValueError, match="ціна має бути додатною"):
        price_fork(Decimal(0))
    with pytest.raises(ValueError, match="відсоток вилки"):
        price_fork(Decimal(10), percent=100)
    with pytest.raises(ValueError, match="відсоток вилки"):
        price_fork(Decimal(10), percent=0)


def test_price_fork_accepts_the_edges_of_the_allowed_range():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    assert "грн" in price_fork_comment(price_fork(Decimal("0.90")))
    assert "99–101 грн" in price_fork_comment(price_fork(Decimal(100), percent=1))


def test_price_fork_rounds_the_floor_down_not_to_the_nearest():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    assert "56,7–69,3 грн" in price_fork_comment(price_fork(Decimal(63)))


def test_the_axis_loses_its_trailing_punctuation_not_the_leading_word():
    from decimal import Decimal

    from komora.core.mandate import price_fork, price_fork_comment

    comment = price_fork_comment(price_fork(Decimal(100)), kind="інший цільнозерновий, 400 г.")
    assert "інший цільнозерновий, 400 г у межах" in comment


def test_an_axis_that_fills_the_field_exactly_still_fits():
    from decimal import Decimal

    from komora.core.mandate import MAX_COMMENT_LENGTH, price_fork, price_fork_comment

    price = Decimal(100)
    longest = next(
        n
        for n in range(1, 400)
        if ("х" * n) not in price_fork_comment(price_fork(price), kind="х" * n)
    ) - 1
    assert len(price_fork_comment(price_fork(price), kind="х" * longest)) == MAX_COMMENT_LENGTH


def test_comment_exactly_at_the_limit_is_not_trimmed():
    chain = [alt("Пармезан")]
    natural = build_comment(chain=chain).comment
    at_limit = build_comment(chain=chain, max_length=len(natural))

    assert at_limit.comment == natural
    assert at_limit.dropped == ()

    tighter = build_comment(chain=chain, max_length=len(natural) - 1)
    assert len(tighter.comment) <= len(natural) - 1


def test_the_fork_says_what_the_price_is_for():
    said = price_fork_comment(
        price_fork(Decimal("719"), percent=10, per="кг"), kind="інший курячий рулет домашній в/с"
    )

    assert "у межах 669–769 грн/кг" in said


def test_a_piece_needs_no_such_word():
    said = price_fork_comment(price_fork(Decimal("520"), percent=10), kind="інша марка")

    assert "у межах 470–570 грн" in said
    assert "/" not in said.split("грн")[0] + "грн"


def test_the_fork_carries_the_form_wish():
    said = price_fork_comment(
        price_fork(Decimal("57"), percent=10),
        kind="інший цільнозерновий пшеничний",
        wish="без нарізки",
    )

    assert said.endswith("; без нарізки")


def test_the_wish_is_dropped_before_the_fork_itself():
    bare = price_fork_comment(
        price_fork(Decimal("57"), percent=10), kind="інший цільнозерновий пшеничний"
    )
    said = price_fork_comment(
        price_fork(Decimal("57"), percent=10),
        kind="інший цільнозерновий пшеничний",
        wish="без нарізки",
        max_length=len(bare) + 1,
    )

    assert said == bare


def test_a_named_axis_that_does_not_fit_falls_back_with_the_wish_kept():
    said = price_fork_comment(
        price_fork(Decimal("57"), percent=10),
        kind="інший цільнозерновий пшеничний хліб на заквасці без дріжджів 400 г",
        wish="нарізаний",
        max_length=100,
    )

    assert said.startswith("якщо немає — рівноцінна заміна того самого виду")
    assert said.endswith("; нарізаний")


def test_a_wish_that_fills_the_field_exactly_still_fits():
    bare = price_fork_comment(price_fork(Decimal("57"), percent=10), kind="інший цільнозерновий")
    exact = len(bare) + len("; нарізаний")

    assert price_fork_comment(
        price_fork(Decimal("57"), percent=10),
        kind="інший цільнозерновий",
        wish="нарізаний",
        max_length=exact,
    ).endswith("; нарізаний")

    assert (
        price_fork_comment(
            price_fork(Decimal("57"), percent=10),
            kind="інший цільнозерновий",
            wish="нарізаний",
            max_length=exact - 1,
        )
        == bare
    )


def test_an_axis_that_fills_the_field_exactly_survives_the_wish_check():
    bare = price_fork_comment(price_fork(Decimal("57"), percent=10), kind="інший цільнозерновий")

    assert (
        price_fork_comment(
            price_fork(Decimal("57"), percent=10),
            kind="інший цільнозерновий",
            wish="нарізаний",
            max_length=len(bare),
        )
        == bare
    )


def test_the_fork_is_one_object_so_the_screen_and_the_collector_cannot_diverge():
    fork = price_fork(Decimal("34.90"))

    assert (fork.low, fork.high) == (Decimal("31.41"), Decimal("38.39"))
    assert fork.phrase == "у межах 31,41–38,39 грн"
    assert fork.phrase in price_fork_comment(fork)


def test_the_fork_carries_the_measure_of_its_own_price():
    weighed = price_fork(Decimal("719"), per="кг")

    assert weighed.per == "кг"
    assert weighed.phrase == "у межах 669–769 грн/кг"
    assert price_fork(Decimal("719"), per="   ").phrase == "у межах 669–769 грн"


def test_the_fork_path_carries_the_shelf_life_too():
    comment = price_fork_comment(
        price_fork(Decimal("54.90")),
        kind="інше молоко 2,5%, 900 г",
        shelf_life="термін придатності не менше ніж до 30.08",
    )
    assert comment.index("49,41–60,39 грн") < comment.index("термін придатності")


def test_the_wish_is_cut_before_the_shelf_life():
    comment = price_fork_comment(
        price_fork(Decimal("54.90")),
        shelf_life="термін придатності не менше ніж до 30.08",
        wish="нарізаний",
        max_length=130,
    )
    assert "термін придатності не менше ніж до 30.08" in comment
    assert "нарізаний" not in comment
    assert len(comment) <= 130


def test_a_head_that_does_not_fit_drops_its_tails_with_it():
    comment = price_fork_comment(
        price_fork(Decimal(100)),
        kind="дуже довга вісь " * 40,
        shelf_life="термін придатності не менше ніж до 30.08",
        wish="нарізаний",
    )
    assert "дуже довга вісь" not in comment
    assert "того самого виду" in comment
    assert "термін придатності не менше ніж до 30.08" in comment
