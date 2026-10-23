from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from komora.api.schemas import Place, PlaceOption
from komora.core.location import Address, Location, source_note

MAX_PLACES = 64


@dataclass(frozen=True, slots=True)
class Known:

    location: Location
    saved: tuple[Address, ...] = field(default_factory=tuple)
    branch: str | None = None


_PLACES: OrderedDict[str, Known] = OrderedDict()


def remember(known: Known, *, owner: str) -> Known:
    _PLACES[owner] = known
    _PLACES.move_to_end(owner)
    while len(_PLACES) > MAX_PLACES:
        _PLACES.popitem(last=False)
    return known


def recall(owner: str) -> Known | None:
    known = _PLACES.get(owner)
    if known is not None:
        _PLACES.move_to_end(owner)
    return known


def forget(owner: str) -> None:
    _PLACES.pop(owner, None)


def forget_all() -> None:
    _PLACES.clear()


def option_of(address: Address) -> PlaceOption:
    return PlaceOption(
        id=address.id,
        label=address.label,
        tag=address.tag,
        latitude=address.latitude,
        longitude=address.longitude,
        city=address.city,
        street=address.street,
        house=address.house,
        confirmed=address.confirmed,
    )


def to_place(known: Known) -> Place:
    address = known.location.address
    return Place(
        address=address.label if address else None,
        tag=address.tag if address else None,
        branch=known.branch,
        branch_id=known.location.branch_id,
        source=known.location.source.value,
        note=source_note(known.location.source),
        delivery_types=sorted(known.location.offered or ()),
        saved=[option_of(item) for item in known.saved],
    )


__all__ = [
    "MAX_PLACES",
    "Known",
    "forget",
    "forget_all",
    "option_of",
    "recall",
    "remember",
    "to_place",
]
