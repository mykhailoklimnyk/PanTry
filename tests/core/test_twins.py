from __future__ import annotations

from decimal import Decimal

from komora.core.twins import (
    ALL_GUEST,
    NO_ANSWER,
    NO_KEEP,
    NOT_IN_TURNS,
    NOT_SAME,
    SAID_GUEST,
    SAID_MODEL,
    SAID_OWN,
    Group,
    Row,
    Verdict,
    group_key,
    groups,
    head_word,
    judge,
    together,
)


def _row(intent: str, article: str, **kw: object) -> Row:
    return Row(intent=intent, article=article, name=kw.pop("name", intent), **kw)  # type: ignore[arg-type]


def test_two_intents_of_one_kind_phrase_become_one_group():
    rows = [
        _row("Томат", "32589", phrase="томати"),
        _row("Томат Azura Черрі сливка", "455724", phrase="томати"),
        _row("Банан", "32485", phrase="банани"),
    ]

    pairs = groups(rows)

    assert [group.key for group in pairs] == ["томати"]
    assert pairs[0].articles == ("32589", "455724")


def test_a_row_without_a_phrase_falls_back_to_the_head_of_the_kind_key():
    rows = [
        _row("Лимонад Geo Natura", "789516", kind_key="лимонад geo"),
        _row("Лимонад лимон", "739664", kind_key="лимонад лимон"),
    ]

    pairs = groups(rows)

    assert [group.key for group in pairs] == ["лимонад"]


def test_head_word_and_group_key_read_the_phrase_first():
    assert head_word("Вода Мінеральна Карпатська") == "вода"
    assert head_word("   ") == ""
    assert group_key(phrase=" Томати ", kind_key="томат la") == "томати"
    assert group_key(phrase="", kind_key="томат la") == "томат"


def test_a_lonely_row_is_never_a_group():
    assert groups([_row("Банан", "32485", phrase="банани")]) == ()


def test_a_row_without_any_key_is_not_grouped_with_the_other_nameless_ones():
    rows = [_row("", "1"), _row("", "2")]

    assert groups(rows) == ()


def test_the_model_may_call_a_pair_two_different_needs():
    group = Group(
        key="вода питна",
        rows=(
            _row("Вода дитяча Малятко", "386913", phrase="вода питна", own_article=True),
            _row("Вода питна Моршинка Спорт", "369992", phrase="вода питна", own_article=True),
        ),
    )

    judged = judge([group], {"вода питна": Verdict(key="вода питна", same=False)})

    assert judged.dropped == ()
    assert judged.left == {"вода питна": NOT_SAME}


def test_a_guests_own_word_is_never_dropped():
    group = Group(
        key="томати",
        rows=(
            _row("помідори", "32589", phrase="томати", guest_word=True),
            _row("Томат Azura Черрі сливка", "455724", phrase="томати"),
        ),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="455724")})

    assert [drop.intent for drop in judged.dropped] == ["Томат Azura Черрі сливка"]
    assert judged.dropped[0].kept_intent == "помідори"
    assert judged.guest_kept == ("томати",)
    assert judged.dropped[0].why == SAID_GUEST


def test_a_group_of_guest_words_only_stays_whole_and_says_why():
    group = Group(
        key="томати",
        rows=(
            _row("помідори", "1", phrase="томати", guest_word=True),
            _row("черрі", "2", phrase="томати", guest_word=True),
        ),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="1")})

    assert judged.dropped == ()
    assert judged.left == {"томати": ALL_GUEST}


def test_the_own_article_from_the_receipts_beats_the_substitute_the_model_kept():
    group = Group(
        key="томати",
        rows=(
            _row("Томат", "32589", phrase="томати", own_article=True),
            _row("Томат Azura Черрі сливка", "455724", phrase="томати"),
        ),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="455724")})

    assert [drop.intent for drop in judged.dropped] == ["Томат Azura Черрі сливка"]
    assert judged.dropped[0].kept_name == "Томат"
    assert judged.own_kept == ("томати",)
    assert judged.dropped[0].why == SAID_OWN


def test_the_reason_of_the_model_wins_over_our_own_wording():
    group = Group(
        key="томати",
        rows=(
            _row("Томат", "32589", phrase="томати", own_article=True),
            _row("Томат Azura", "455724", phrase="томати"),
        ),
    )

    judged = judge(
        [group],
        {"томати": Verdict(key="томати", same=True, keep="32589", why="обидва томати на салат")},
    )

    assert judged.dropped[0].why == "обидва томати на салат"


def test_without_a_reason_the_default_says_it_was_the_model():
    group = Group(
        key="томати",
        rows=(
            _row("Томат", "32589", phrase="томати", own_article=True),
            _row("Томат Azura", "455724", phrase="томати"),
        ),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="32589")})

    assert judged.dropped[0].why == SAID_MODEL
    assert judged.own_kept == ()


def test_a_group_the_model_did_not_answer_stays_and_names_its_own_reason():
    group = Group(
        key="томати",
        rows=(_row("Томат", "1", phrase="томати"), _row("Томат Azura", "2", phrase="томати")),
    )

    judged = judge([group], {})

    assert judged.dropped == ()
    assert judged.left == {"томати": NO_ANSWER}


def test_a_verdict_that_keeps_an_article_outside_the_group_changes_nothing():
    group = Group(
        key="томати",
        rows=(_row("Томат", "1", phrase="томати"), _row("Томат Azura", "2", phrase="томати")),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="999")})

    assert judged.dropped == ()
    assert judged.left == {"томати": NO_KEEP}


def test_quantities_are_not_summed_because_the_module_never_touches_them():
    kept = _row("Томат", "32589", phrase="томати", own_article=True, price=Decimal("74.87"))
    group = Group(
        key="томати",
        rows=(kept, _row("Томат Azura", "455724", phrase="томати", price=Decimal("154.00"))),
    )

    judged = judge([group], {"томати": Verdict(key="томати", same=True, keep="32589")})

    assert judged.intents == ("Томат Azura",)
    assert kept.price == Decimal("74.87")


def test_the_dropped_intents_are_named_one_by_one():
    group = Group(
        key="лимонад",
        rows=(
            _row("Лимонад Кремовий", "789516", phrase="лимонад", own_article=True),
            _row("Лимонад груша", "739664", phrase="лимонад"),
            _row("Лимонад лимон", "739665", phrase="лимонад"),
        ),
    )

    judged = judge([group], {"лимонад": Verdict(key="лимонад", same=True, keep="789516")})

    assert judged.intents == ("Лимонад груша", "Лимонад лимон")


BREAD = frozenset({"Хлібобулочні вироби"})
VEG = frozenset({"Овочі"})


def test_different_phrases_of_one_section_become_one_group_keyed_by_the_section():
    rows = [
        _row("Хліб Рум'янець", "813640", phrase="хліб", sections=BREAD),
        _row("Банан", "32485", phrase="банани"),
        _row("Булка подова", "596031", phrase="булка", sections=BREAD),
        _row("Багет подовий", "375210", phrase="багет", sections=BREAD),
    ]

    pairs = groups(rows)

    assert [group.key for group in pairs] == ["хлібобулочні вироби"]
    assert pairs[0].articles == ("813640", "596031", "375210")
    assert pairs[0].by_section


def test_a_phrase_pair_never_mixes_with_its_section_neighbours():
    rows = [
        _row("Томат", "1", phrase="томати", sections=VEG),
        _row("Томат черрі", "2", phrase="томати", sections=VEG),
        _row("Огірок", "3", phrase="огірки", sections=VEG),
    ]

    pairs = groups(rows)

    assert [(group.key, group.articles, group.by_section) for group in pairs] == [
        ("томати", ("1", "2"), False)
    ]


def test_a_section_group_without_one_common_section_is_keyed_by_its_phrases():
    rows = [
        _row("Хліб", "1", phrase="хліб", sections=frozenset({"А"})),
        _row("Булка", "2", phrase="булка", sections=frozenset({"А", "Б"})),
        _row("Багет", "3", phrase="багет", sections=frozenset({"Б"})),
    ]

    (group,) = groups(rows)

    assert group.key == "багет / булка / хліб"
    assert group.by_section


def test_one_phrase_keeps_its_own_key_even_when_the_rows_share_a_section():
    rows = [
        _row("Томат", "1", phrase="томати", sections=VEG),
        _row("Томат черрі", "2", phrase="томати", sections=VEG),
    ]

    assert [group.key for group in groups(rows)] == ["томати"]


def test_a_section_without_a_second_row_groups_nothing():
    rows = [
        _row("Хліб", "1", phrase="хліб", sections=BREAD),
        _row("Томат", "2", phrase="томати", sections=VEG),
    ]

    assert groups(rows) == ()


def test_a_partial_verdict_drops_only_the_named_rows():
    group = Group(
        key="мішане",
        rows=(
            _row("Хліб", "1", phrase="хліб"),
            _row("Булка", "2", phrase="булка"),
            _row("Огірок", "3", phrase="огірки"),
        ),
    )

    judged = judge([group], {"мішане": Verdict(key="мішане", same=True, keep="1", drop=("2",))})

    assert [drop.intent for drop in judged.dropped] == ["Булка"]


def test_a_partial_verdict_still_keeps_the_own_article_among_its_rows():
    group = Group(
        key="мішане",
        rows=(
            _row("Хліб", "1", phrase="хліб"),
            _row("Булка", "2", phrase="булка", own_article=True),
            _row("Огірок", "3", phrase="огірки", own_article=True),
        ),
    )

    judged = judge([group], {"мішане": Verdict(key="мішане", same=True, keep="1", drop=("2",))})

    assert [drop.intent for drop in judged.dropped] == ["Хліб"]
    assert judged.dropped[0].kept_name == "Булка"
    assert judged.dropped[0].why == SAID_OWN


def test_a_partial_verdict_never_drops_a_guest_word():
    group = Group(
        key="мішане",
        rows=(
            _row("Хліб", "1", phrase="хліб"),
            _row("булка", "2", phrase="булка", guest_word=True),
        ),
    )

    judged = judge([group], {"мішане": Verdict(key="мішане", same=True, keep="2", drop=("1",))})

    assert [drop.intent for drop in judged.dropped] == ["Хліб"]
    assert judged.dropped[0].kept_name == "булка"


def _section(*rows: Row) -> Group:
    return Group(key="відділ", rows=rows, by_section=True)


def test_a_section_group_drops_only_what_was_bought_in_turns():
    group = _section(
        _row("Хліб", "1", phrase="хліб", bought=frozenset({"d1", "d2"})),
        _row("Булка", "2", phrase="булка", bought=frozenset({"d3"})),
        _row("Огірок", "3", phrase="огірки", bought=frozenset({"d1"})),
    )

    judged = judge([group], {"відділ": Verdict(key="відділ", same=True, keep="1")})

    assert [drop.intent for drop in judged.dropped] == ["Булка"]


def test_a_section_group_keeps_a_row_without_purchases():
    group = _section(
        _row("Хліб", "1", phrase="хліб", bought=frozenset({"d1"})),
        _row("Булка", "2", phrase="булка"),
    )

    judged = judge([group], {"відділ": Verdict(key="відділ", same=True, keep="1")})

    assert judged.dropped == ()
    assert judged.left == {"відділ": NOT_IN_TURNS}


def test_the_pairs_say_how_the_guest_buys_them():
    group = _section(
        _row("Хліб", "1", phrase="хліб", bought=frozenset({"d1", "d2"})),
        _row("Булка", "2", phrase="булка", bought=frozenset({"d3"})),
        _row("Огірок", "3", phrase="огірки", bought=frozenset({"d1"})),
        _row("Заміна", "4", phrase="заміна"),
    )

    assert together(group) == (
        "1 і 2: по черзі, тобто вдома одне замінює інше -- в один похід 0 з 3 походів "
        "з будь-яким із двох",
        "1 і 3: разом -- в один похід 1 з 2 походів з будь-яким із двох",
        "2 і 3: по черзі, тобто вдома одне замінює інше -- в один похід 0 з 2 походів "
        "з будь-яким із двох",
    )
