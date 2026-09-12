from decimal import Decimal

from komora.core.cheaper import better


def item(unit: float | None, price: str | None) -> tuple[float | None, Decimal | None]:
    return (unit, Decimal(price) if price is not None else None)


def pick(chosen, others, floor=None):
    kwargs = {} if floor is None else {"floor": Decimal(str(floor))}
    return better(
        chosen,
        others,
        unit_price=lambda i: i[0],
        price=lambda i: i[1],
        **kwargs,
    )


def test_cheaper_by_unit_and_by_line_is_worth_saying():
    mine = item(10.0, "100")
    other = item(7.0, "80")

    assert pick(mine, [other]) == other


def test_cheaper_by_unit_but_dearer_by_line_is_not():
    mine = item(10.0, "100")
    bigger = item(7.0, "260")

    assert pick(mine, [bigger]) is None


def test_a_saving_inside_the_noise_stays_silent():
    mine = item(10.0, "100")
    barely = item(9.5, "95")

    assert pick(mine, [barely]) is None
    assert pick(mine, [barely], floor=0.01) == barely


def test_the_best_of_several_wins_not_the_first():
    mine = item(10.0, "100")
    good = item(8.0, "90")
    best = item(5.0, "70")

    assert pick(mine, [good, best]) == best


def test_a_candidate_without_a_common_unit_is_skipped_not_guessed():
    mine = item(10.0, "100")

    assert pick(mine, [item(None, "50"), item(0.0, "40")]) is None


def test_a_line_without_its_own_unit_price_says_nothing():
    assert pick(item(None, "100"), [item(5.0, "70")]) is None
    assert pick(item(10.0, None), [item(5.0, "70")]) is None


def test_nothing_to_compare_is_the_same_answer_as_nothing_cheaper():
    assert pick(item(10.0, "100"), []) is None
