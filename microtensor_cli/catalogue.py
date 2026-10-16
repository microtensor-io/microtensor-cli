from __future__ import annotations

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
    live: bool

    @property
    def general(self) -> bool:
        return self.kind == GENERAL

    @property
    def label(self) -> str:
        return self.title or self.id

    def describe(self) -> str:
        parts = ["General model" if self.general else "Certified specialist"]
        if self.context:
            parts.append(f"{context_label(self.context)} context")
        if self.tool_calling:
            parts.append("tools")
        if self.vision:
            parts.append("images")
        if self.usd_in_per_mtok is not None and self.usd_out_per_mtok is not None:
            parts.append(
                f"${self.usd_in_per_mtok:g} in, ${self.usd_out_per_mtok:g} out per 1M tokens"
            )
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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
        live=any(m.live for m in found),
    )


def offered(models: Sequence[Model]) -> list[Model]:
    return [auto_model(models), *general(models)]
