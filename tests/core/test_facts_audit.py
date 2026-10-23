from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from komora.core.facts_audit import SPREAD_FLOOR, audit


@dataclass(frozen=True, slots=True)
class _Fact:
    keeps: str | None = "days"
    sanity: str | None = "з'їдають за раз"
    rhythm_lies: bool | None = True
    per_day: Decimal | None = None
    per_day_unit: str | None = None


def _sentence(i: int) -> str:
    return "зникає з дому " + "о" * (i + 1)


def _rows(count: int, **kwargs) -> dict[str, _Fact]:
    return {
        f"вид {i}": _Fact(
            keeps="days" if i % 2 else "weeks",
            sanity=_sentence(i),
            rhythm_lies=bool(i % 3),
            **kwargs,
        )
        for i in range(count)
    }


def test_a_healthy_run_says_its_numbers_and_nothing_else():
    report = audit(_rows(40))

    assert report.clean
    assert report.rows == 40 and report.with_keeps == 40 and report.with_sanity == 40
    assert report.unique_sanity == 40
    assert report.lies == 26
    assert report.lines() == [
        "перевірка: рядків 40, зі стелею 40, з глуздом 40, різних речень 40, "
        "«ритм бреше» 26",
        "  зауважень немає",
    ]


def test_a_shelf_life_without_sense_is_the_bug_of_the_day():
    rows = _rows(40)
    rows["вид 0"] = _Fact(keeps="days", sanity=None)

    report = audit(rows)

    assert [f.rule for f in report.findings] == ["половина відповіді"]
    assert report.findings[0].note == "мітки зі стелею, але без глузду: 1"
    assert "  половина відповіді: мітки зі стелею" in report.lines()[1]


def test_sense_without_a_shelf_life_is_the_same_rule_from_the_other_side():
    rows = _rows(40)
    rows["вид 0"] = _Fact(keeps=None, sanity="щось")

    finding = audit(rows).findings[0]
    assert finding.rule == "половина відповіді"
    assert finding.note == "мітки з глуздом, але без стелі: 1"


def test_a_row_with_neither_half_is_neither_finding():
    rows = _rows(40)
    rows["вид 0"] = _Fact(keeps=None, sanity=None)

    assert audit(rows).clean


def test_one_sentence_on_many_kinds_is_a_copy_not_an_answer():
    rows = _rows(40)
    for i in range(5):
        rows[f"вид {i}"] = _Fact(sanity="витрачається рівномірно")

    report = audit(rows)

    assert [f.rule for f in report.findings] == ["одне речення на багатьох"]
    assert report.findings[0].note == "«витрачається рівномірно» -- 5 разів з 40"


def test_a_sentence_that_repeats_within_the_measured_tail_is_not_a_finding():
    rows = _rows(40)
    rows["вид 0"] = _Fact(sanity="витрачається рівномірно")
    rows["вид 1"] = _Fact(sanity="витрачається рівномірно")

    assert audit(rows).clean


def test_an_invented_number_in_a_sentence_is_named():
    rows = _rows(40)
    rows["вид 0"] = _Fact(sanity="вистачає на 3 дні")

    finding = audit(rows).findings[0]
    assert finding.rule == "вигадане число"
    assert finding.note == "речень із цифрою: 1, напр. «вистачає на 3 дні»"


def test_a_sentence_in_another_alphabet_means_the_model_switched_language():
    rows = _rows(40)
    rows["вид 0"] = _Fact(sanity="eaten in one sitting")

    finding = audit(rows).findings[0]
    assert finding.rule == "чужа абетка"
    assert finding.note == "речень без кирилиці: 1, напр. «eaten in one sitting»"


def test_a_norm_without_a_unit_is_a_number_without_an_axis():
    rows = _rows(40)
    rows["вид 0"] = _Fact(per_day=Decimal("2"), per_day_unit=None)
    rows["вид 1"] = _Fact(per_day=Decimal("5"), per_day_unit=None)

    finding = audit(rows).findings[0]
    assert finding.rule == "число без одиниці"
    assert finding.note == "норма без «г» чи «шт»: 2"
    assert audit(_rows(40, per_day=Decimal("2"), per_day_unit="г")).clean


def test_a_verdict_that_is_always_the_same_is_not_a_verdict():
    always = {f"вид {i}": _Fact(sanity=_sentence(i)) for i in range(SPREAD_FLOOR)}
    never = {
        f"вид {i}": _Fact(sanity=_sentence(i), rhythm_lies=False)
        for i in range(SPREAD_FLOOR)
    }

    for rows in (always, never):
        finding = next(f for f in audit(rows).findings if f.rule == "вирок без розкиду")
        assert finding.note == f"«ритм бреше» однаковий у всіх {SPREAD_FLOOR}"


def test_below_the_floor_one_answer_for_all_is_still_legal():
    rows = {f"вид {i}": _Fact(sanity=_sentence(i)) for i in range(SPREAD_FLOOR - 1)}

    assert "вирок без розкиду" not in [f.rule for f in audit(rows).findings]


def test_one_shelf_tier_on_everything_is_a_finding_too():
    rows = {
        f"вид {i}": _Fact(sanity=_sentence(i), rhythm_lies=bool(i % 3))
        for i in range(SPREAD_FLOOR)
    }

    finding = audit(rows).findings[0]
    assert finding.rule == "ярус без розкиду"
    assert finding.note == f"стеля зберігання одна на всі {SPREAD_FLOOR}"


def test_an_empty_run_is_an_answer_and_not_a_crash():
    report = audit({})

    assert report.clean and report.rows == 0
