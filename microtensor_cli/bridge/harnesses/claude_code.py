from __future__ import annotations

import os
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
from microtensor_cli.catalogue import LONG_CONTEXT, Model
from microtensor_cli.config import user_home
from microtensor_cli.errors import CliError
from microtensor_cli.files import dump_json, load_json

NAME = "claude-code"
TIERS = (
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)
ENV_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", *TIERS)
TOP_KEYS = ("model", "modelPicker", "apiKeyHelper")
HEADER = f"{TOOL_HEADER}: {NAME}"


def settings_path() -> Path:
    found = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(found) if found else user_home() / ".claude"
    return root / "settings.json"


def picker_id(model: Model) -> str:
    return f"{model.id}[1m]" if model.context >= LONG_CONTEXT else model.id


def _doc(raw: bytes | None, path: Path) -> dict[str, Any]:
    found = load_json(raw, path, empty={})
    if not isinstance(found, dict):
        raise CliError(f"{path} does not hold a JSON object, so it was left untouched")
    return found


class ClaudeCode:
    name = NAME
    title = "Claude Code"
    after = "Start a new Claude Code session to use it."
    processes: Mapping[str, str] = MappingProxyType({})

    def installed(self) -> str:
        return ""

    def targets(self) -> Targets:
        return Targets(files=(settings_path(),))

    def apply(self, current: Capture, ctx: Context) -> Change:
        path = settings_path()
        doc = _doc(current.file(path), path)
        env = doc.get("env")
        if not isinstance(env, dict):
            env = {}
            doc["env"] = env
        chosen = picker_id(ctx.model)
        env["ANTHROPIC_BASE_URL"] = ctx.base_url
        env["ANTHROPIC_AUTH_TOKEN"] = ctx.key
        env["ANTHROPIC_CUSTOM_HEADERS"] = HEADER
        for var in TIERS:
            env[var] = chosen
        doc["model"] = chosen
        helper = doc.pop("apiKeyHelper", None)
        doc["modelPicker"] = {
            "replaceBuiltInOptions": True,
            "options": [
                {"model": picker_id(m), "label": m.label, "description": m.describe()}
                for m in ctx.models
            ],
        }
        change = Change()
        change.files[path] = dump_json(doc)
        change.private.add(path)
        change.changed = [
            f"{path}: env.ANTHROPIC_BASE_URL, env.ANTHROPIC_AUTH_TOKEN, "
            "env.ANTHROPIC_CUSTOM_HEADERS",
            f"{path}: model and every model tier set to {chosen}",
            f"{path}: modelPicker lists {len(ctx.models)} Microtensor models",
        ]
        if helper is not None:
            change.changed.append(f"{path}: apiKeyHelper removed while bridged")
        change.notes.append(
            "Claude Code sends every request to Microtensor while bridged, including "
            "background tasks, so all tiers point at the chosen model."
        )
        return change

    def revert(self, current: Capture, snapshot: Capture) -> Change:
        path = settings_path()
        then_raw = snapshot.file(path)
        then = _doc(then_raw, path)
        now = _doc(current.file(path), path)
        restore_paths(now, then, [("env", k) for k in ENV_KEYS])
        restore_paths(now, then, [(k,) for k in TOP_KEYS])
        prune(now, then, [("env",)])
        change = Change()
        change.files[path] = finish_json(now, then, then_raw, {})
        change.changed = [f"{path}: Microtensor settings removed, your earlier values put back"]
        return change

    def state(self, current: Capture) -> State:
        path = settings_path()
        try:
            doc = _doc(current.file(path), path)
        except CliError:
            return State(bridged=False, model="", where=str(path))
        env = as_dict(doc.get("env"))
        bridged = TOOL_HEADER in str(env.get("ANTHROPIC_CUSTOM_HEADERS", ""))
        model = str(doc.get("model", "")).removesuffix("[1m]") if bridged else ""
        return State(bridged=bridged, model=model, where=str(path))
