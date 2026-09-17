from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

DIGEST_CHARS = 8


@dataclass(frozen=True, slots=True)
class Prompt:

    name: str
    text: str
    digest: str


REGISTRY: dict[str, Prompt] = {}


def register(name: str, text: str) -> Prompt:
    if not text.strip():
        raise ValueError(f"промпт «{name}» порожній: хешувати нема чого")
    digest = sha256(text.encode("utf-8")).hexdigest()[:DIGEST_CHARS]
    known = REGISTRY.get(name)
    if known is not None and known.text != text:
        raise ValueError(
            f"промпт «{name}» уже зареєстровано з іншим текстом "
            f"({known.digest} проти {digest}): одне ім'я -- один текст"
        )
    prompt = Prompt(name=name, text=text, digest=digest)
    REGISTRY[name] = prompt
    return prompt


def digest_of(name: str) -> str:
    try:
        return REGISTRY[name].digest
    except KeyError:
        raise KeyError(f"промпта «{name}» немає в реєстрі: {sorted(REGISTRY)}") from None


def parts_in(text: str) -> tuple[str, ...]:
    found = [(text.index(p.text), name) for name, p in REGISTRY.items() if p.text in text]
    return tuple(name for _, name in sorted(found))


def stamp(family: str, text: str) -> str:
    names = parts_in(text)
    if not names:
        return f"{family}[поза реєстром]"
    if names == (family,):
        return f"{family}@{digest_of(family)}"
    prefix = family + "."
    parts = [
        f"{name.removeprefix(prefix)}@{digest_of(name)}"
        if name.startswith(prefix)
        else f"{name}@{digest_of(name)}"
        for name in names
    ]
    return f"{family}[{','.join(parts)}]"


def load_all() -> None:
    import importlib
    import pkgutil

    import komora.agent

    for info in pkgutil.walk_packages(komora.agent.__path__, komora.agent.__name__ + "."):
        importlib.import_module(info.name)


__all__ = [
    "DIGEST_CHARS",
    "REGISTRY",
    "Prompt",
    "digest_of",
    "load_all",
    "parts_in",
    "register",
    "stamp",
]
