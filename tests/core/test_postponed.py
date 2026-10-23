from __future__ import annotations

from komora.core.postponed import FIX_ORDER, Remedy, in_fix_order


def test_every_remedy_has_a_place_in_the_order() -> None:
    assert set(FIX_ORDER) == set(Remedy)
    assert len(FIX_ORDER) == len(Remedy)


def test_the_order_runs_from_one_touch_here_to_nothing_the_guest_can_do() -> None:
    assert FIX_ORDER == (
        Remedy.REFILL,
        Remedy.MANUAL,
        Remedy.NEXT_RUN,
        Remedy.PROMO,
        Remedy.SHELF,
    )


def test_scrambled_pipeline_still_comes_out_in_fix_order() -> None:
    scrambled = [
        (Remedy.SHELF, "паляничка"),
        (Remedy.PROMO, "мюслі"),
        (Remedy.NEXT_RUN, "вершки"),
        (Remedy.MANUAL, "999"),
        (Remedy.REFILL, "олія"),
    ]
    assert in_fix_order(scrambled) == ["олія", "999", "вершки", "мюслі", "паляничка"]


def test_inside_one_remedy_the_pipeline_order_survives() -> None:
    same = [
        (Remedy.PROMO, "авокадо"),
        (Remedy.PROMO, "лохина"),
        (Remedy.PROMO, "цибуля"),
    ]
    assert in_fix_order(same) == ["авокадо", "лохина", "цибуля"]


def test_two_sentences_about_one_action_stand_together() -> None:
    mixed = [
        (Remedy.SHELF, "береш по акції, але на цей слот не знайшлось"),
        (Remedy.PROMO, "чекаю акції"),
        (Remedy.SHELF, "закінчилось, але на цей слот не знайшлось"),
    ]
    assert in_fix_order(mixed) == [
        "чекаю акції",
        "береш по акції, але на цей слот не знайшлось",
        "закінчилось, але на цей слот не знайшлось",
    ]


def test_nothing_postponed_is_an_empty_list_not_a_failure() -> None:
    assert in_fix_order([]) == []
