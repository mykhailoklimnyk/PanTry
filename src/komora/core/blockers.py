from __future__ import annotations

BRANCH_MISMATCH = "komora.cart.branch"

KNOWN: dict[str, str] = {
    BRANCH_MISMATCH: (
        "кошик у «Сільпо» прив'язаний до іншого магазину, ніж той, для якого я "
        "збирав: у кожної філії свій асортимент, тож ці товари туди не стануть"
    ),
    "product.offer.status.not_available": (
        "частину товарів «Сільпо» не прийняло: їх зняли з продажу вже після збірки"
    ),
    "product.offer.stock.max": (
        "частину кількостей зрізано: на полиці лишилось менше, ніж я просив"
    ),
    "product.offer.not_found": ("частини товарів у каталозі вже немає — їх треба замінити іншими"),
    "product.offer.price.changed": "ціна змінилась між збіркою і записом",
    "order.adult.is_not_confirmed": (
        "у кошику є товари 18+ (алкоголь): «Сільпо» попросить підтвердити вік при оформленні"
    ),
}

UNKNOWN = "«Сільпо» відмовило частині рядків і назвало причину так: {code}"

WARNING = "«Сільпо» попереджає: {code}"


def explain(codes: list[str]) -> list[str]:
    seen: list[str] = []
    for code in codes:
        key = code.strip()
        if not key:
            continue
        said = KNOWN.get(key) or UNKNOWN.format(code=key)
        if said not in seen:
            seen.append(said)
    return seen


def explain_warnings(codes: list[str]) -> list[str]:
    seen: list[str] = []
    for code in codes:
        key = code.strip()
        if not key:
            continue
        said = KNOWN.get(key) or WARNING.format(code=key)
        if said not in seen:
            seen.append(said)
    return seen


def worth_retrying(codes: list[str]) -> bool:
    return any(
        code.strip() in {"product.offer.status.not_available", "product.offer.not_found"}
        for code in codes
    )


__all__ = ["BRANCH_MISMATCH", "KNOWN", "UNKNOWN", "explain", "worth_retrying"]
