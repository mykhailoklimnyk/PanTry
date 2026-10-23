from __future__ import annotations

from komora.core.blockers import KNOWN, explain, worth_retrying


def test_kody_z_zhyvoho_prohonu_maiut_svoi_slova() -> None:
    said = explain(
        [
            "product.offer.status.not_available",
            "product.offer.stock.max",
            "product.offer.not_found",
        ]
    )
    assert len(said) == 3
    assert all(note and "product.offer" not in note for note in said)


def test_nevidomyi_kod_ne_znykaie_a_nazyvaie_sebe() -> None:
    said = explain(["shipment.weight.max"])
    assert len(said) == 1
    assert "shipment.weight.max" in said[0]


def test_odyn_i_toi_samyi_kod_ne_povtoriuietsia() -> None:
    assert explain(["product.offer.stock.max"] * 10) == explain(["product.offer.stock.max"])


def test_poriadok_kodiv_zberihaietsia() -> None:
    said = explain(["product.offer.not_found", "product.offer.stock.max"])
    assert said[0] == KNOWN["product.offer.not_found"]


def test_porozhnie_i_smittia_ne_staiut_rechenniam() -> None:
    assert explain([]) == []
    assert explain(["", "   "]) == []


def test_perezbirka_radytsia_lyshe_tam_de_vona_shchos_minyaie() -> None:
    assert worth_retrying(["product.offer.status.not_available"]) is True
    assert worth_retrying(["product.offer.not_found"]) is True
    assert worth_retrying(["product.offer.stock.max"]) is False


def test_odyn_likovnyi_kod_sered_neliikovnykh_rady_ne_skasovuie() -> None:
    assert worth_retrying(["product.offer.stock.max", "product.offer.not_found"]) is True


def test_bez_blokeriv_perezbiraty_nema_choho() -> None:
    assert worth_retrying([]) is False
    assert worth_retrying(["shipment.weight.max"]) is False


def test_kozhen_vidomyi_kod_maie_neporozhnie_rechennia() -> None:
    assert all(text.strip() for text in KNOWN.values())
    assert len(set(KNOWN.values())) == len(KNOWN)


def test_an_empty_code_is_skipped_without_stopping_the_rest():
    from komora.core.blockers import explain_warnings

    assert explain(["", "product.offer.price.changed"]) == ["ціна змінилась між збіркою і записом"]
    assert explain_warnings(["", "order.delivery.late"]) == [
        "«Сільпо» попереджає: order.delivery.late"
    ]
