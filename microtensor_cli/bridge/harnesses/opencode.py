from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from microtensor_cli.bridge.base import (
    TOOL_HEADER,
    Capture,
    Change,
    Context,
    State,
    Targets,
    as_dict,
    finish_json,
    prune,
    restore_paths,
)
from microtensor_cli.catalogue import DEFAULT_CONTEXT, DEFAULT_OUTPUT, Model
from microtensor_cli.config import xdg_config
from microtensor_cli.errors import CliError
from microtensor_cli.files import dump_json, load_json

NAME = "opencode"
PROVIDER = "microtensor"
SCHEMA = "https://opencode.ai/config.json"


def config_path() -> Path:
    return xdg_config() / "opencode" / "opencode.json"


def _doc(raw: bytes | None, path: Path) -> dict[str, Any]:
    found = load_json(raw, path, empty={})
    if not isinstance(found, dict):
        raise CliError(f"{path} does not hold a JSON object, so it was left untouched")
    return found


def _model(m: Model) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": m.label,
        "limit": {
            "context": m.context or DEFAULT_CONTEXT,
            "output": m.max_output or DEFAULT_OUTPUT,
        },
        "tool_call": m.tool_calling,
    }
    if m.vision:
        entry["modalities"] = {"input": ["text", "image"], "output": ["text"]}
    return entry


class OpenCode:
    name = NAME
    title = "OpenCode"
    after = "Restart OpenCode and pick a model with /models."
    processes: Mapping[str, str] = MappingProxyType({})

    def installed(self) -> str:
        return ""

    def targets(self) -> Targets:
        return Targets(files=(config_path(),))

    def apply(self, current: Capture, ctx: Context) -> Change:
        path = config_path()
        raw = current.file(path)
        doc = _doc(raw, path)
        if raw is None:
            doc["$schema"] = SCHEMA
        provider = doc.get("provider")
        if not isinstance(provider, dict):
            provider = {}
            doc["provider"] = provider
        provider[PROVIDER] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Microtensor",
            "options": {
                "baseURL": f"{ctx.base_url}/v1",
                "apiKey": ctx.key,
                "headers": {TOOL_HEADER: NAME},
            },
            "models": {m.id: _model(m) for m in ctx.models},
        }
        doc["model"] = f"{PROVIDER}/{ctx.model.id}"
        change = Change()
        change.files[path] = dump_json(doc)
        change.private.add(path)
        change.changed = [
            f"{path}: provider.{PROVIDER} with {len(ctx.models)} models and your key",
            f"{path}: model = {PROVIDER}/{ctx.model.id}",
        ]
        if (path.parent / "opencode.jsonc").exists():
            change.notes.append(
                f"{path.parent / 'opencode.jsonc'} also exists; OpenCode merges both files."
            )
        return change

    def revert(self, current: Capture, snapshot: Capture) -> Change:
        path = config_path()
        then_raw = snapshot.file(path)
        then = _doc(then_raw, path)
        now = _doc(current.file(path), path)
        restore_paths(now, then, [("model",), ("provider", PROVIDER), ("$schema",)])
        prune(now, then, [("provider",)])
        change = Change()
        change.files[path] = finish_json(now, then, then_raw, {})
        change.changed = [f"{path}: Microtensor provider removed, your earlier values put back"]
        return change

    def state(self, current: Capture) -> State:
        path = config_path()
        try:
            doc = _doc(current.file(path), path)
        except CliError:
            return State(bridged=False, model="", where=str(path))
        provider = as_dict(doc.get("provider"))
        bridged = PROVIDER in provider
        model = str(doc.get("model", "")).removeprefix(f"{PROVIDER}/") if bridged else ""
        return State(bridged=bridged, model=model, where=str(path))
