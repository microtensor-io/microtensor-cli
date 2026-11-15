from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

AUTO = "mt/auto"
GENERAL = "general"
CERTIFIED = "certified"
LONG_CONTEXT = 1_000_000
DEFAULT_CONTEXT = 131_072
DEFAULT_OUTPUT = 8_192


@dataclass(frozen=True, slots=True)
class Band:
    input_tokens_below: int | None
    usd_per_request: float


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    kind: str
    title: str
    context: int
    max_output: int
    tool_calling: bool
    vision: bool
    usd_in_per_mtok: float | None
    usd_out_per_mtok: float | None
    usd_per_request: float | None
    schedule: tuple[Band, ...]
    live: bool

    @property
    def general(self) -> bool:
        return self.kind == GENERAL

    @property
    def label(self) -> str:
        return self.title or self.id

    @property
    def per_request(self) -> str:
        found = [band.usd_per_request for band in self.schedule]
        if not found and self.usd_per_request is not None and self.usd_per_request > 0:
            found = [self.usd_per_request]
        if not found:
            return ""
        low, high = f"${min(found):g}", f"${max(found):g}"
        return f"{low} per request" if low == high else f"{low} to {high} per request"

    @property
    def token_prices(self) -> tuple[float, float] | None:
        if self.schedule or self.usd_in_per_mtok is None or self.usd_out_per_mtok is None:
            return None
        if self.per_request and self.usd_in_per_mtok <= 0 and self.usd_out_per_mtok <= 0:
            return None
        return self.usd_in_per_mtok, self.usd_out_per_mtok

    def describe(self) -> str:
        parts = ["General model" if self.general else "Certified specialist"]
        if self.context:
            parts.append(f"{context_label(self.context)} context")
        if self.tool_calling:
            parts.append("tools")
        if self.vision:
            parts.append("images")
        tokens = self.token_prices
        if tokens is not None:
            parts.append(f"${tokens[0]:g} in, ${tokens[1]:g} out per 1M tokens")
        if self.per_request:
            parts.append(self.per_request)
        if not self.live:
            parts.append("not served right now")
        return ", ".join(parts)


def context_label(tokens: int) -> str:
    if tokens >= LONG_CONTEXT:
        return f"{tokens / LONG_CONTEXT:g}M"
    if tokens >= 1000:
        return f"{round(tokens / 1024)}K"
    return str(tokens)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        found = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return found if math.isfinite(found) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _schedule(value: Any) -> tuple[Band, ...]:
    found: list[Band] = []
    for band in value if isinstance(value, list) else []:
        if not isinstance(band, Mapping):
            continue
        price = _finite(band.get("usd_per_request"))
        if price is None or price <= 0:
            continue
        below = _finite(band.get("input_tokens_below"))
        found.append(Band(int(below) if below is not None and below >= 1 else None, price))
    return tuple(found)


def parse(entry: Mapping[str, Any]) -> Model:
    model_id = str(entry.get("id", ""))
    prices = _mapping(entry.get("prices"))
    modalities = [str(m) for m in entry.get("modalities") or []]
    capacity = _mapping(entry.get("capacity"))
    kind = str(entry.get("kind") or (CERTIFIED if model_id != AUTO else "router"))
    return Model(
        id=model_id,
        kind=kind,
        title=str(entry.get("title") or ""),
        context=int(entry.get("context") or 0),
        max_output=int(entry.get("max_output") or 0),
        tool_calling=bool(entry.get("tool_calling", False)),
        vision="image" in modalities,
        usd_in_per_mtok=_number(prices.get("usd_in_per_mtok")),
        usd_out_per_mtok=_number(prices.get("usd_out_per_mtok")),
        usd_per_request=_finite(prices.get("usd_per_request")),
        schedule=_schedule(prices.get("schedule")),
        live=bool(capacity.get("live", False)),
    )


def parse_list(payload: Mapping[str, Any]) -> list[Model]:
    return [parse(entry) for entry in payload.get("data") or [] if isinstance(entry, Mapping)]


def general(models: Sequence[Model]) -> list[Model]:
    return [m for m in models if m.general]


def find(models: Sequence[Model], model_id: str) -> Model | None:
    return next((m for m in models if m.id == model_id), None)


def auto_model(models: Sequence[Model]) -> Model:
    found = general(models)
    context = max((m.context for m in found), default=DEFAULT_CONTEXT) or DEFAULT_CONTEXT
    output = max((m.max_output for m in found), default=DEFAULT_OUTPUT) or DEFAULT_OUTPUT
    return Model(
        id=AUTO,
        kind="router",
        title="Microtensor auto",
        context=context,
        max_output=output,
        tool_calling=any(m.tool_calling for m in found) or not found,
        vision=any(m.vision for m in found),
        usd_in_per_mtok=None,
        usd_out_per_mtok=None,
        usd_per_request=None,
        schedule=(),
        live=any(m.live for m in found),
    )


def offered(models: Sequence[Model]) -> list[Model]:
    return [auto_model(models), *general(models)]
