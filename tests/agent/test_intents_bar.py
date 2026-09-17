from komora.agent.basket import Naming
from komora.agent.steps.intents import at_bar
from komora.core.bar import DrinkKind


def test_a_kind_named_a_drink_is_at_the_bar_and_the_guest_word_overrules_the_guess():
    beer = "Пиво Hike Blanche світле з/б"
    named = {
        "пиво hike": Naming(intent="пиво", subtype="", drink=DrinkKind.LIGHT, drink_known=True)
    }
    assert at_bar(named, beer, {})
    plain = {"пиво hike": Naming(intent="пиво")}
    assert not at_bar(plain, beer, {}), "без групи напою -- не бар"
    assert at_bar(plain, beer, {"пиво": DrinkKind.LIGHT}), "гість сказав «це напій» -- бар"
    assert not at_bar(named, "Молоко Ферма 2,5%", {}), "неназваний вид не судиться"
