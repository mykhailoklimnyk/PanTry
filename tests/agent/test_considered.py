from komora.agent.basket import MAX_CONSIDERED, _considered


def _card(article: str, name: str) -> dict:
    return {"externalProductId": article, "name": name, "price": 10.0}


def test_the_guests_kind_comes_first_and_the_rest_keeps_the_shelf_order():
    chosen = _card("1", "Лохина BlueBerry Club 125 г")
    options = [
        _card("2", "Гумка жувальна Orbit Лохина"),
        _card("3", "Йогурт Галичина лохина 2,5%"),
        _card("4", "Корм для дорослих собак Club 4 Paws"),
        _card("5", "Йогурт Молокія лохина"),
        _card("6", "Батончик Snickers"),
        chosen,
        _card("7", "Лохина свіжа 250 г"),
        _card("8", "Лохина заморожена 300 г"),
    ]
    shown = _considered("лохина", options, chosen)
    assert [p["externalProductId"] for p in shown] == ["7", "8", "2", "3", "4"]
    assert len(shown) == MAX_CONSIDERED
    assert chosen not in shown


def test_question_chips_show_the_guests_kind_and_not_the_shelf_neighbours():
    from komora.agent.basket import _ask_picks

    cards = [
        _card("1", "Паста креветкова Veladis з авокадо с/б"),
        _card("2", "Соус Zanuy Guacamole Salsa з авокадо"),
        _card("3", "Авокадо Eat Me"),
        _card("4", "Маска для обличчя тканинна Mond'Sub авокадо живильна"),
    ]
    assert [p["externalProductId"] for p in _ask_picks("авокадо хасс стиглий", cards)] == ["3"]
    strangers = cards[:2]
    assert _ask_picks("авокадо хасс стиглий", strangers) == strangers, "без свого -- як було"
