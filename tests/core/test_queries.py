from komora.agent.basket import STOP_WORDS, norm_name
from komora.core.queries import (
    dedupe,
    head,
    kind_words,
    narrow,
    norm_query,
    one_product,
    words,
)


def test_words_split_on_punctuation_too():
    assert words("Сир кисломолочний, 9%/в.у") == ["Сир", "кисломолочний", "9%", "в", "у"]


def test_head_takes_the_first_words():
    assert head("Сир кисломолочний Простонаше 9%", 2) == "Сир кисломолочний"
    assert head("Сир кисломолочний Простонаше 9%", 1) == "Сир"


def test_kind_words_drop_brands_numbers_and_packaging():
    assert kind_words("Пюре Mark&Mart запечене яблучк-морквочка без цукру") == ("Пюре запечене")
    assert kind_words("Сир кисломолочний Простонаше 9% в/у") == "Сир кисломолочний"


def test_the_ladder_goes_from_precise_to_broad():
    assert narrow("Пюре Mark&Mart запечене яблучк-морквочка без цукру") == (
        "Пюре запечене",
        "Пюре Mark&Mart",
        "Пюре",
    )


def test_the_ladder_has_no_duplicates():
    assert narrow("Сир кисломолочний Простонаше 9% в/у") == ("Сир кисломолочний", "Сир")


def test_a_name_with_nowhere_to_narrow_gives_nothing():
    assert narrow("Молоко") == ()
    assert narrow("  Молоко  ") == ()


def test_a_fully_latin_name_still_narrows_by_words():
    assert narrow("Coca-Cola Zero 0.5 л") == ("Coca-Cola Zero", "Coca-Cola")


def test_short_tails_are_not_a_kind():
    assert kind_words("Креветка гриль ЕК") == "Креветка гриль"
    assert "ЕК" not in narrow("Креветка гриль ЕК")[0]


def test_the_ladder_never_repeats_the_name_it_started_from():
    assert narrow("Сир кисломолочний") == ("Сир",)


def test_a_phrase_with_a_preposition_is_one_product():
    assert one_product("Сендвіч з баликом")
    assert one_product("Сир без лактози")
    assert one_product("Корм для котів")
    assert one_product("Йогурт із чорницею")


def test_a_list_joined_by_and_is_still_a_list():
    assert not one_product("хліб і молоко")
    assert not one_product("хліб молоко чай")
    assert not one_product("молоко та хліб")


def test_the_preposition_is_a_whole_word_not_a_letter_inside_one():
    assert not one_product("зубна паста")
    assert not one_product("морозиво пломбір")


def test_the_case_of_the_preposition_does_not_matter():
    assert one_product("Сендвіч З баликом")


class TestSpoluchnyky:

    def test_abo_ne_staie_namirom(self) -> None:
        assert norm_name("або") in STOP_WORDS
        assert norm_name("чи") in STOP_WORDS

    def test_spoluchnyk_ne_perestav_buty_slovom_u_frazi(self) -> None:
        assert one_product("Печиво без цукру") is True


class TestNormQuery:

    def test_rehistr_i_probily_ne_rakhuiutsia(self) -> None:
        assert norm_query("  СИР   Твердий ") == "сир твердий"

    def test_odnakovi_zapyty_daiut_odyn_kliuch(self) -> None:
        assert norm_query("Сендвіч") == norm_query("  сендвіч ")

    def test_rizni_zapyty_daiut_rizni_kliuchi(self) -> None:
        assert norm_query("паляниця") != norm_query("паляничка")

    def test_porozhnie_daie_porozhnie(self) -> None:
        assert norm_query("   ") == ""

    def test_perenos_riadka_tezh_probil(self) -> None:
        assert norm_query("сир" + chr(10) + "твердий") == "сир твердий"


class TestDedupe:
    def test_namiry_shcho_riznyatsia_rehistrom_zlyvaiutsia(self) -> None:
        assert dedupe(["Вино", "вино", "хлібці"]) == ["Вино", "хлібці"]

    def test_lyshaietsia_persha_forma(self) -> None:
        assert dedupe(["вино", "Вино"]) == ["вино"]

    def test_probily_ne_robliat_z_odnoho_namiru_dva(self) -> None:
        assert dedupe(["сир  твердий", "сир твердий"]) == ["сир  твердий"]

    def test_rizni_namiry_ne_zlyvaiutsia(self) -> None:
        assert dedupe(["сир твердий", "сир кисломолочний"]) == [
            "сир твердий",
            "сир кисломолочний",
        ]

    def test_porozhnie_ne_staie_namirom(self) -> None:
        assert dedupe(["", "   ", "хліб"]) == ["хліб"]
