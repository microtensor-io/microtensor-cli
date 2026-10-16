from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from microtensor_cli.bridge.base import (
    MISSING,
    Capture,
    Change,
    Context,
    State,
    Targets,
    as_dict,
    get_path,
)
from microtensor_cli.bridge.editors.safestorage import SafeStorageError, buffer_json, encrypt
from microtensor_cli.config import app_data

NAME = "cursor"
APP_KEY = (
    "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl"
    ".persistentStorage.applicationUser"
)
SEALED_ROW = "secret://cursorAuth/openAIKey"
LEGACY_KEY = "cursorAuth/openAIKey"
MARKER = "mtensorAddedModels"
LISTS = ("userAddedModels", "modelOverrideEnabled")
DEFAULT_MODE = "composer"
TOP_KEYS = ("openAIBaseUrl", "useOpenAIKey")


def user_data() -> Path:
    return app_data() / "Cursor"


def db_path() -> Path:
    return user_data() / "User" / "globalStorage" / "state.vscdb"


def local_state() -> Path:
    return user_data() / "Local State"


def _blob(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        found = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return found if isinstance(found, dict) else {}


def _compact(doc: dict[str, Any]) -> str:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


class Cursor:
    name = NAME
    title = "Cursor"
    after = "Open Cursor and pick a Microtensor model in the model menu."
    processes: Mapping[str, str] = MappingProxyType(
        {"win32": "Cursor.exe", "darwin": "Cursor", "linux": "cursor"}
    )

    def installed(self) -> str:
        return (
            ""
            if user_data().exists()
            else f"Cursor does not seem to be installed here (no {user_data()})"
        )

    def targets(self) -> Targets:
        return Targets(rows=((db_path(), (APP_KEY, SEALED_ROW, LEGACY_KEY)),))

    def apply(self, current: Capture, ctx: Context) -> Change:
        db = db_path()
        blob = _blob(current.row(db, APP_KEY))
        ids = [m.id for m in ctx.models]
        added = [str(i) for i in blob.get(MARKER) or []]
        ai = blob.get("aiSettings")
        if not isinstance(ai, dict):
            ai = {}
            blob["aiSettings"] = ai
        for field in LISTS:
            kept = [x for x in ai.get(field) or [] if x not in added]
            ai[field] = kept + [i for i in ids if i not in kept]
        blob[MARKER] = ids
        configs = ai.get("modelConfig")
        if not isinstance(configs, dict):
            configs = {}
            ai["modelConfig"] = configs
        for mode in {*configs, DEFAULT_MODE}:
            held = as_dict(configs.get(mode))
            configs[mode] = {
                **held,
                "modelName": ctx.model.id,
                "selectedModels": [{"modelId": ctx.model.id, "parameters": []}],
            }
        blob["openAIBaseUrl"] = f"{ctx.base_url}/v1"
        blob["useOpenAIKey"] = True
        rows: dict[str, str | None] = {APP_KEY: _compact(blob)}
        change = Change()
        try:
            sealed, note = encrypt("Cursor", local_state(), ctx.key)
            rows[SEALED_ROW] = buffer_json(sealed)
            if note:
                change.notes.append(note)
        except SafeStorageError as exc:
            rows[LEGACY_KEY] = ctx.key
            change.notes.append(
                f"Cursor's key store could not be written ({exc}). If Cursor asks for an "
                "OpenAI API key, paste your Microtensor key in Settings, Models."
            )
        change.rows[db] = rows
        change.changed = [
            f"{db}: OpenAI base URL override set to {ctx.base_url}/v1 with your key",
            f"{db}: {len(ids)} Microtensor models added, {ctx.model.id} selected",
        ]
        change.notes.append(
            "Cursor sends custom key requests through its own servers, uses them for chat "
            "only, and some agent features refuse custom keys. Tab completion stays on Cursor."
        )
        return change

    def revert(self, current: Capture, snapshot: Capture) -> Change:
        db = db_path()
        then_value = snapshot.row(db, APP_KEY)
        then = _blob(then_value)
        now = _blob(current.row(db, APP_KEY))
        added = {str(i) for i in now.get(MARKER) or []}
        for key in TOP_KEYS:
            if key in then:
                now[key] = copy.deepcopy(then[key])
            else:
                now.pop(key, None)
        now.pop(MARKER, None)
        ai = now.get("aiSettings")
        then_ai = as_dict(then.get("aiSettings"))
        if isinstance(ai, dict):
            for field in LISTS:
                before = then_ai.get(field) or []
                kept = [x for x in ai.get(field) or [] if x not in added or x in before]
                if kept or field in then_ai:
                    ai[field] = kept
                else:
                    ai.pop(field, None)
            configs = ai.get("modelConfig")
            then_configs = as_dict(then_ai.get("modelConfig"))
            if isinstance(configs, dict):
                for mode in list(configs):
                    if mode in then_configs:
                        configs[mode] = copy.deepcopy(then_configs[mode])
                    else:
                        del configs[mode]
                if not configs and get_path(then, ("aiSettings", "modelConfig")) is MISSING:
                    ai.pop("modelConfig", None)
            if not ai and "aiSettings" not in then:
                now.pop("aiSettings", None)
        if now == then:
            value = then_value
        elif then_value is None and not now:
            value = None
        else:
            value = _compact(now)
        change = Change()
        change.rows[db] = {
            APP_KEY: value,
            SEALED_ROW: snapshot.row(db, SEALED_ROW),
            LEGACY_KEY: snapshot.row(db, LEGACY_KEY),
        }
        change.changed = [
            f"{db}: base URL, key and Microtensor models removed, your settings put back"
        ]
        return change

    def state(self, current: Capture) -> State:
        db = db_path()
        blob = _blob(current.row(db, APP_KEY))
        bridged = MARKER in blob
        model = ""
        if bridged:
            found = get_path(blob, ("aiSettings", "modelConfig", DEFAULT_MODE, "modelName"))
            model = "" if found is MISSING else str(found)
        return State(bridged=bridged, model=model, where=str(db))
