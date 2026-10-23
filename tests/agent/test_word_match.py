from komora.agent.basket import name_matches, related_by_kind


def test_olives_are_not_butter_even_though_they_share_four_letters():
    assert not name_matches("маслини", "Масло солодковершкове Ферма 73%")
    assert not related_by_kind("маслини", "Масло солодковершкове Ферма 73%")
    assert name_matches("огірки", "Огірок Ніжинський")
    assert name_matches("яблука", "Яблуко Голден")
    assert name_matches("молоко", "Молоком Ферма")
    assert name_matches("банан", "Бананів кетяг")
