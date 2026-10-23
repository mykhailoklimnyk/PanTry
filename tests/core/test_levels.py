from komora.core.levels import Level, Seen, fold, fresh_links, own_chain, parts


def rows(*levels: tuple[str, str, bool]) -> list[Level]:
    return [Level(id=row, intent=intent, urgent=urgent) for row, intent, urgent in levels]


def test_two_rows_of_one_intent_become_a_group():
    folded = fold(rows(("a", "йогурт", True), ("b", "йогурт", False)))
    assert folded.groups == 1
    assert folded.rows == 2
    assert folded.group_of == {"a": "йогурт", "b": "йогурт"}


def test_a_lone_intent_is_not_a_group():
    folded = fold(rows(("a", "йогурт", True), ("b", "хліб", False)))
    assert folded.groups == 0
    assert folded.rows == 0
    assert folded.group_of == {}
    assert folded.order == ("a", "b")


def test_the_split_intent_is_not_folded():
    folded = fold(rows(("a", "вода питна", True), ("b", "вода питна", False)), apart=["вода питна"])
    assert folded.groups == 0
    assert folded.group_of == {}
    assert folded.order == ("a", "b")


def test_splitting_one_intent_leaves_the_others_folded():
    folded = fold(
        rows(
            ("a", "вода питна", True),
            ("b", "вода питна", False),
            ("c", "йогурт", False),
            ("d", "йогурт", False),
        ),
        apart=["вода питна"],
    )
    assert folded.groups == 1
    assert folded.group_of == {"c": "йогурт", "d": "йогурт"}


def test_an_empty_split_name_splits_nothing():
    folded = fold(rows(("a", "йогурт", True), ("b", "йогурт", False)), apart=["", "  "])
    assert folded.groups == 1


def test_rows_without_a_name_never_become_a_group():
    folded = fold(rows(("a", "", True), ("b", "", False), ("c", "", False)))
    assert folded.groups == 0
    assert folded.group_of == {}
    assert folded.order == ("a", "b", "c")


def test_members_of_a_group_stand_together():
    folded = fold(
        rows(
            ("a", "йогурт", True),
            ("b", "хліб", True),
            ("c", "йогурт", False),
        )
    )
    assert folded.order == ("a", "c", "b")


def test_the_group_stands_where_its_most_urgent_row_stood():
    folded = fold(
        rows(
            ("гострий", "хліб", True),
            ("сам", "сіль", False),
            ("тихий", "хліб", False),
        )
    )
    assert folded.order == ("гострий", "тихий", "сам")


def test_the_order_inside_a_group_is_the_order_it_came_in():
    folded = fold(
        rows(
            ("перший", "йогурт", True),
            ("другий", "йогурт", True),
            ("третій", "йогурт", False),
        )
    )
    assert folded.order == ("перший", "другий", "третій")


def test_nothing_is_lost_and_nothing_is_doubled():
    given = rows(
        ("a", "йогурт", False),
        ("b", "хліб", True),
        ("c", "йогурт", True),
        ("d", "", False),
        ("e", "хліб", False),
    )
    folded = fold(given)
    assert sorted(folded.order) == sorted(level.id for level in given)
    assert len(folded.order) == len(given)


def test_an_empty_pantry_folds_into_nothing():
    folded = fold([])
    assert folded.order == ()
    assert folded.groups == 0
    assert folded.rows == 0


def test_three_rows_of_one_intent_are_one_group_of_three():
    folded = fold(
        rows(("a", "сир", False), ("b", "сир", False), ("c", "сир", True), ("d", "сіль", False))
    )
    assert folded.groups == 1
    assert folded.rows == 3
    assert folded.order == ("a", "b", "c", "d")


def test_two_intents_give_two_groups():
    folded = fold(
        rows(
            ("a", "сир", False),
            ("b", "йогурт", False),
            ("c", "сир", False),
            ("d", "йогурт", False),
        )
    )
    assert folded.groups == 2
    assert folded.rows == 4
    assert folded.order == ("a", "c", "b", "d")


def seen(label: str, receipts: int, days: int | None, unit: str = "шт") -> Seen:
    return Seen(label=label, unit=unit, receipts=receipts, days_since=days)


def test_the_freshest_article_stands_first():
    got = parts([seen("Старе", 9, 200), seen("Свіже", 1, 3)], recent_days=90)
    assert [part.label for part in got] == ["Свіже", "Старе"]


def test_freshness_is_the_threshold_and_not_the_order():
    got = parts([seen("Позаторішнє", 4, 400)], recent_days=90)
    assert got[0].fresh is False


def test_the_edge_of_the_window_is_still_fresh():
    assert parts([seen("Рівно", 1, 90)], recent_days=90)[0].fresh is True
    assert parts([seen("На день пізніше", 1, 91)], recent_days=90)[0].fresh is False


def test_an_article_without_a_date_goes_last_and_is_not_fresh():
    got = parts([seen("Без дати", 50, None), seen("Учора", 1, 1)], recent_days=90)
    assert [part.label for part in got] == ["Учора", "Без дати"]
    assert got[-1].fresh is False


def test_the_more_bought_wins_a_tie():
    got = parts([seen("Рідше", 2, 5), seen("Частіше", 8, 5)], recent_days=90)
    assert [part.label for part in got] == ["Частіше", "Рідше"]


def test_an_empty_unit_stays_empty():
    assert parts([seen("Ваговий", 3, 2, unit="")], recent_days=90)[0].unit == ""


def test_nothing_bought_gives_nothing():
    assert parts([], recent_days=90) == ()


def test_the_same_name_from_two_sources_is_one_row():
    made = parts(
        [
            Seen(label="Куряче філе", unit="кг", receipts=3, days_since=12),
            Seen(label="Куряче філе", unit="кг", receipts=2, days_since=4),
        ],
        recent_days=30,
    )

    assert [part.label for part in made] == ["Куряче філе"]


def test_purchases_add_up_and_the_freshest_date_wins():
    made = parts(
        [
            Seen(label="Банан", unit="кг", receipts=3, days_since=40),
            Seen(label="Банан", unit="кг", receipts=2, days_since=4),
        ],
        recent_days=30,
    )

    assert made[0].receipts == 5
    assert made[0].days_since == 4
    assert made[0].fresh is True


def test_the_number_the_guest_reads_stops_lying():
    seen = [Seen(label="Огірок", unit="кг", receipts=1, days_since=day) for day in (2, 9)]
    seen.append(Seen(label="Огірок екстра", unit="кг", receipts=1, days_since=5))

    assert len(parts(seen, recent_days=30)) == 2


def test_a_date_that_nobody_knows_does_not_beat_a_known_one():
    made = parts(
        [
            Seen(label="Хліб", unit="шт", receipts=1, days_since=None),
            Seen(label="Хліб", unit="шт", receipts=1, days_since=3),
        ],
        recent_days=30,
    )

    assert made[0].days_since == 3
    assert made[0].fresh is True


def test_two_unknown_dates_stay_unknown():
    made = parts(
        [
            Seen(label="Сіль", unit="шт", receipts=1, days_since=None),
            Seen(label="Сіль", unit="шт", receipts=2, days_since=None),
        ],
        recent_days=30,
    )

    assert made[0].days_since is None
    assert made[0].receipts == 3


def own(article: str, label: str, days: int | None, receipts: int = 3) -> Seen:
    return Seen(label=label, unit="300г", receipts=receipts, days_since=days, article=article)


def test_the_guests_other_fresh_article_becomes_a_link():
    chain = own_chain(
        [own("101", "Йогурт Живинка", 3), own("102", "Йогурт Галичина", 10)],
        head="101",
        recent_days=90,
    )

    assert [one.article for one in chain] == ["102"]


def test_the_head_itself_is_never_a_link():
    assert own_chain([own("101", "Йогурт Живинка", 3)], head="101", recent_days=90) == ()


def test_what_the_guest_stopped_buying_is_not_his_own_any_more():
    chain = own_chain(
        [own("102", "Йогурт Галичина", 400), own("103", "Йогурт Ферма", 12)],
        head="101",
        recent_days=90,
    )

    assert [one.article for one in chain] == ["103"]


def test_the_freshness_threshold_takes_what_stands_exactly_on_it():
    chain = own_chain([own("102", "Йогурт Галичина", 90)], head="101", recent_days=90)

    assert [one.article for one in chain] == ["102"]


def test_an_article_without_a_date_stays_out():
    assert own_chain([own("102", "Йогурт Галичина", None)], head="101", recent_days=90) == ()


def test_an_article_without_a_number_stays_out():
    assert own_chain([own("", "Йогурт Галичина", 3)], head="101", recent_days=90) == ()


def test_links_go_freshest_first():
    chain = own_chain(
        [own("103", "Йогурт Ферма", 30), own("102", "Йогурт Галичина", 5)],
        head="101",
        recent_days=90,
    )

    assert [one.article for one in chain] == ["102", "103"]


def test_one_article_never_becomes_two_links():
    chain = own_chain(
        [own("102", "Йогурт Галичина", 5), own("102", "Йогурт Галичина 2,5%", 40)],
        head="101",
        recent_days=90,
    )

    assert [one.article for one in chain] == ["102"]
    assert chain[0].days_since == 5, "лишається найсвіжіше написання, а не перше-ліпше"


def test_equal_dates_are_ranked_by_how_often_the_guest_takes_it():
    chain = own_chain(
        [own("103", "Йогурт Ферма", 7, receipts=1), own("102", "Йогурт Галичина", 7, receipts=9)],
        head="101",
        recent_days=90,
    )

    assert [one.article for one in chain] == ["102", "103"]


def test_an_agreed_chain_loses_the_article_the_guest_stopped_buying():
    kept, dropped = fresh_links(
        ("101", "102"),
        [own("101", "Морозиво Tonitto", 458), own("102", "Морозиво Ласка", 12)],
        recent_days=90,
    )

    assert kept == ("102",)
    assert dropped == ("101",)


def test_a_link_the_guest_never_bought_is_not_stale_but_unknown():
    kept, dropped = fresh_links(("999",), [own("101", "Морозиво Tonitto", 458)], recent_days=90)

    assert kept == ("999",)
    assert dropped == ()
