from collections.abc import Iterable
from enum import StrEnum


class Remedy(StrEnum):

    REFILL = "refill"
    """Кнопка «Закрити решту тижня»: один дотик, не виходячи з екрана."""
    MANUAL = "manual"
    """Гість додає руками в кошик «Сільпо»: назви для пошуку в нас немає."""
    NEXT_RUN = "next_run"
    """Спитаємо наступним прогоном: стеля питань -- про гостя, а не про дані."""
    PROMO = "promo"
    """Чекає акції: вид, який гість без знижки не бере (#265)."""
    SHELF = "shelf"
    """На цей слот у «Сільпо» не знайшлось: інший слот або інші слова."""


FIX_ORDER = (
    Remedy.REFILL,
    Remedy.MANUAL,
    Remedy.NEXT_RUN,
    Remedy.PROMO,
    Remedy.SHELF,
)
"""Від найвиправнішого до невиправного.

Межу між сусідами ставить не смак, а ЦІНА ДІЇ для гостя: дотик на цьому ж
екрані дешевший за похід у чужий застосунок, той -- за очікування наступного
прогону, а найдорожче коштує те, чого гість не виправить узагалі, бо товару
на полиці цього слота немає.
"""


def in_fix_order[T](tagged: Iterable[tuple[Remedy, T]]) -> list[T]:
    rank = {remedy: place for place, remedy in enumerate(FIX_ORDER)}
    return [item for _, item in sorted(tagged, key=lambda pair: rank[pair[0]])]
