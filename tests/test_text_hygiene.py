from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from text_lint import clean, replace_apostrophes, report, targets

from komora.core.homoglyphs import fix_word, is_allowed, mixed_words


def test_the_tree_is_clean() -> None:
    root = Path(__file__).resolve().parents[1]
    problems = [
        line
        for path in targets()
        for line in report(path.relative_to(root), path.read_text(encoding="utf-8"))
    ]
    assert not problems, "\n".join(
        ["текст забруднився, полагодити: uv run python scripts/text_lint.py --fix", *problems]
    )


def test_catches_the_case_that_prompted_it() -> None:
    found = mixed_words("// час: він не namір, він обставина")
    assert found, "гомогліф у коментарі мусить знайтись"
    word, _, healed = found[0]
    assert word == "namір"
    assert not healed


def test_the_script_of_the_line_decides_the_direction() -> None:
    assert fix_word("сiль", "cyr") == "сіль"
    assert fix_word("Sаlt", "lat") == "Salt"


@pytest.mark.parametrize(
    ("bad", "good"),
    [
        ("днí", "дні"),
        ("Мoлoкo", "Молоко"),
        ("Cир", "Сир"),
        ("рaхyнok", "рахунок"),
    ],
)
def test_diacritics_and_lookalikes_heal(bad: str, good: str) -> None:
    assert fix_word(bad, "cyr") == good


def test_apostrophe_never_breaks_a_string_literal() -> None:
    line = '        _parse(\'["не", "обʼєкт"]\', "m")'
    assert replace_apostrophes(Path("t.py"), line) == line

    assert replace_apostrophes(Path("t.ts"), "label: 'курʼєр',") == 'label: "кур\'єр",'


def test_code_survives_the_fix() -> None:
    source = "const left = total - spent\n// сума - це не тире\n"
    fixed = clean(Path("x.ts"), source)
    assert "total - spent" in fixed
    assert "сума — це не тире" in fixed


def test_svelte_expression_is_code_even_on_a_cyrillic_line() -> None:
    line = "  на {uahRound(Math.abs(a - b))} менше - ніж думали\n"
    fixed = clean(Path("Cart.svelte"), line)

    assert "Math.abs(a - b)" in fixed, "вираз у фігурних дужках — це код"
    assert "менше — ніж думали" in fixed, "а текст поруч усе одно правиться"


def test_svelte_script_is_code_and_its_strings_are_text() -> None:
    source = (
        "<script>\n"
        "  const gap = total - paid;  // різниця - те, що бачить гість\n"
        "  const label = 'товари - знижка';\n"
        "</script>\n"
        '<p title="a - b">курʼєр - завтра</p>\n'
    )
    fixed = clean(Path("Cart.svelte"), source)

    assert "total - paid" in fixed, "арифметика лишається арифметикою"
    assert "різниця — те" in fixed, "коментар — текст"
    assert "'товари — знижка'" in fixed, "рядковий літерал — теж текст"
    assert 'title="a - b"' in fixed, "атрибут не чіпаємо: поруч живуть viewBox і d"
    assert "кур'єр — завтра" in fixed


def test_template_literal_keeps_its_expression() -> None:
    fixed = clean(Path("x.ts"), "const s = `на ${a - b} менше - ніж було`\n")
    assert "${a - b}" in fixed
    assert "менше — ніж було" in fixed


def test_python_code_survives_a_comment_on_the_same_line() -> None:
    source = '"""Докстрінг - теж текст."""\n\ngap = total - paid  # різниця - ось вона\n'
    fixed = clean(Path("x.py"), source)

    assert "total - paid" in fixed
    assert "Докстрінг — теж текст" in fixed
    assert "різниця — ось вона" in fixed


def test_deliberate_typography_stays() -> None:
    for ch in "—«»·₴→№±×✓":
        assert is_allowed(ch), ch
    for ch in "íéàñ​­":
        assert not is_allowed(ch), ch
