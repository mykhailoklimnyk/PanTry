from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any

import jsonschema

from komora.agent.llm import LLM, Decision, Meter, ModelError, Truncated
from komora.core.homoglyphs import fold
from komora.core.prompt import tame
from komora.logging import get_logger

log = get_logger(__name__)

RETRIES = 1

HEDGE_FLOOR_S = 20.0
HEDGE_S_PER_TOKEN = 0.004


def hedge_after(max_tokens: int) -> float:
    return HEDGE_FLOOR_S + HEDGE_S_PER_TOKEN * max_tokens


async def raced(make: Callable[[], Awaitable[Decision]], *, after: float) -> Decision:
    first = asyncio.ensure_future(make())
    pending: set[asyncio.Future[Decision]] = {first}
    try:
        done, _ = await asyncio.wait(pending, timeout=after)
        if done:
            return first.result()
        log.warning("llm.hedged", after_s=round(after, 1))
        pending.add(asyncio.ensure_future(make()))
        failures: list[BaseException] = []
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                error = task.exception()
                if error is None:
                    return task.result()
                failures.append(error)
        raise failures[0]
    finally:
        for task in pending:
            task.cancel()


def _salvage(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    thrown: list[str] = []
    for name, rule in (schema.get("properties") or {}).items():
        if not rule.get("salvage") or rule.get("type") != "array":
            continue
        items = data.get(name)
        if not isinstance(items, list):
            continue
        kept = []
        for index, item in enumerate(items):
            try:
                jsonschema.validate(item, rule["items"])
            except jsonschema.ValidationError as exc:
                thrown.append(f"{name}/{index}: {exc.message}")
                continue
            kept.append(item)
        data[name] = kept
    return thrown


def validate(
    data: dict[str, Any], schema: dict[str, Any], *, model: str, prompt: str = ""
) -> list[str]:
    try:
        jsonschema.validate(data, schema)
        return []
    except jsonschema.ValidationError as exc:
        thrown = _salvage(data, schema)
        if thrown:
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError:
                thrown = []
            else:
                log.warning("llm.salvaged", model=model, prompt=prompt, thrown=thrown)
                return thrown
        path = "/".join(str(part) for part in exc.absolute_path) or "корінь"
        raise ModelError(f"{model}: відповідь не за схемою — {exc.message} ({path})") from exc


class Validated:

    def __init__(self, inner: LLM, meter: Meter | None = None) -> None:
        self._inner = inner
        self.meter = meter if meter is not None else Meter()

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def inner(self) -> LLM:
        return self._inner

    async def decide(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        prompt: str,
        schema_name: str = "decision",
        max_tokens: int = 2048,
        temperature: float | None = None,
    ) -> Decision:
        user = _tamed(user, model=self.model)
        for attempt in range(RETRIES + 1):
            try:
                decision = await raced(
                    lambda: self._inner.decide(
                        system=system,
                        user=user,
                        schema=schema,
                        schema_name=schema_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ),
                    after=hedge_after(max_tokens),
                )
            except Truncated as exc:
                self.meter.burned(exc.usage, self.model)
                log.warning(
                    "llm.truncated",
                    model=self.model,
                    schema=schema_name,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    output_tokens=exc.usage.output_tokens,
                    attempt=attempt + 1,
                )
                if attempt == RETRIES:
                    raise
                continue
            except ModelError as exc:
                self.meter.refused(exc, self.model)
                raise
            break
        log.info(
            "llm.decided",
            model=decision.model or self.model,
            schema=schema_name,
            prompt=prompt,
            ms=decision.duration_ms,
            input_tokens=decision.usage.input_tokens,
            output_tokens=decision.usage.output_tokens,
        )
        self.meter.add(decision)
        _straighten(decision.data, model=decision.model or self.model, prompt=prompt)
        validate(decision.data, schema, model=decision.model or self.model, prompt=prompt)
        return decision


def _tamed(user: str, *, model: str) -> str:
    try:
        payload = json.loads(user)
    except ValueError, TypeError:
        log.warning("llm.foreign_unparsed", model=model, length=len(user))
        return user
    touched: list[str] = []
    healed = _tame_node(payload, touched)
    if not touched:
        return user
    log.info(
        "llm.foreign_tamed",
        model=model,
        fields=len(touched),
        sample=[sha256(x.encode()).hexdigest()[:8] for x in touched[:5]],
    )
    return json.dumps(healed, ensure_ascii=False)


def _tame_node(node: Any, touched: list[str]) -> Any:
    if isinstance(node, str):
        healed, changed = tame(node)
        if changed:
            touched.append(node)
        return healed
    if isinstance(node, dict):
        return {key: _tame_node(value, touched) for key, value in node.items()}
    if isinstance(node, list):
        return [_tame_node(item, touched) for item in node]
    return node


def _straighten(node: Any, *, model: str, prompt: str = "", field: str = "") -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if not isinstance(value, str):
                _straighten(value, model=model, prompt=prompt, field=key)
                continue
            folded = fold(value)
            if folded.changed or folded.odd:
                _named(folded, model=model, prompt=prompt, field=key)
            if folded.changed:
                node[key] = folded.text
    elif isinstance(node, list):
        for item in node:
            _straighten(item, model=model, prompt=prompt, field=field)


def _named(folded, *, model: str, prompt: str, field: str) -> None:
    log.warning(
        "llm.odd_letters",
        model=model,
        prompt=prompt,
        field=field,
        fixed=[f"{sha256(was.encode()).hexdigest()[:8]}->{len(now)}" for was, now in folded.fixed],
        odd=len(folded.odd),
    )


__all__ = ["Validated", "validate"]
