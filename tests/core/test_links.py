from komora.core.links import PRODUCT_URL, product_url


def test_a_real_slug_becomes_a_card_link():
    assert (
        product_url("funduk-v-karameli-790701")
        == "https://silpo.ua/product/funduk-v-karameli-790701"
    )


def test_a_missing_slug_is_not_a_link_to_the_catalogue():
    assert product_url(None) is None
    assert product_url("") is None
    assert product_url("   ") is None


def test_the_slug_is_taken_as_it_came_and_not_glued_blindly():
    assert product_url("  funduk-790701  ") == f"{PRODUCT_URL}funduk-790701"
