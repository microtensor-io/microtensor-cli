from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from microtensor_cli.catalogue import Model
from microtensor_cli.files import dump_json

MISSING: Any = object()
TOOL_HEADER = "X-Microtensor-Tool"


@dataclass(slots=True)
class Capture:
    files: dict[str, bytes | None] = field(default_factory=dict)
    rows: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def file(self, path: Path) -> bytes | None:
        return self.files.get(str(path))

    def row(self, db: Path, key: str) -> str | None:
        return self.rows.get(str(db), {}).get(key)


@dataclass(frozen=True, slots=True)
class Targets:
    files: tuple[Path, ...] = ()
    rows: tuple[tuple[Path, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class Context:
    key: str
    base_url: str
    model: Model
    models: tuple[Model, ...]


@dataclass(slots=True)
class Change:
    files: dict[Path, bytes | None] = field(default_factory=dict)
    rows: dict[Path, dict[str, str | None]] = field(default_factory=dict)
    private: set[Path] = field(default_factory=set)
    changed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class State:
    bridged: bool
    model: str
    where: str


class Harness(Protocol):
    name: str
    title: str
    after: str
    processes: Mapping[str, str]

    def installed(self) -> str: ...

    def targets(self) -> Targets: ...

    def apply(self, current: Capture, ctx: Context) -> Change: ...

    def revert(self, current: Capture, snapshot: Capture) -> Change: ...

    def state(self, current: Capture) -> State: ...


def get_path(doc: Any, path: Sequence[str]) -> Any:
    found = doc
    for part in path:
        if not isinstance(found, dict) or part not in found:
            return MISSING
        found = found[part]
    return found


def set_path(doc: dict[str, Any], path: Sequence[str], value: Any) -> None:
    found = doc
    for part in path[:-1]:
        nxt = found.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            found[part] = nxt
        found = nxt
    found[path[-1]] = value


def del_path(doc: dict[str, Any], path: Sequence[str]) -> None:
    parent = get_path(doc, path[:-1]) if len(path) > 1 else doc
    if isinstance(parent, dict):
        parent.pop(path[-1], None)


def restore_paths(
    now: dict[str, Any], then: dict[str, Any], paths: Iterable[Sequence[str]]
) -> None:
    for path in paths:
        old = get_path(then, path)
        if old is MISSING:
            del_path(now, path)
        else:
            set_path(now, path, copy.deepcopy(old))


def prune(now: dict[str, Any], then: dict[str, Any], parents: Iterable[Sequence[str]]) -> None:
    for path in parents:
        held = get_path(now, path)
        if held == {} and get_path(then, path) is MISSING:
            del_path(now, path)


def finish_json(now: Any, then: Any, then_raw: bytes | None, empty: Any) -> bytes | None:
    if now == then:
        return then_raw
    if then_raw is None and now == empty:
        return None
    return dump_json(now)


def model_rows(models: Sequence[Model]) -> list[str]:
    return [m.id for m in models]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
