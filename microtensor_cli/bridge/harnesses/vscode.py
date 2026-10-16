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
    finish_json,
)
from microtensor_cli.bridge.editors.safestorage import SafeStorageError, buffer_json, encrypt
from microtensor_cli.catalogue import DEFAULT_CONTEXT, DEFAULT_OUTPUT
from microtensor_cli.config import app_data
from microtensor_cli.errors import CliError
from microtensor_cli.files import dump_json, load_json

NAME = "vscode"
VAULT_ID = "chat.lm.secret.microtensor"
SEALED_ROW = f"secret://{VAULT_ID}"
INPUT = "${input:" + VAULT_ID + "}"


def user_data() -> Path:
    return app_data() / "Code"


def models_path() -> Path:
    return user_data() / "User" / "chatLanguageModels.json"


def db_path() -> Path:
    return user_data() / "User" / "globalStorage" / "state.vscdb"


def local_state() -> Path:
    return user_data() / "Local State"


def _ours(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("apiKey") == INPUT


def _doc(raw: bytes | None, path: Path) -> list[Any]:
    found = load_json(raw, path, empty=[])
    if not isinstance(found, list):
        raise CliError(f"{path} does not hold a JSON list, so it was left untouched")
    return found


class VSCode:
    name = NAME
    title = "VS Code"
    after = "Open VS Code, then pick a Microtensor model in the Chat model picker."
    processes: Mapping[str, str] = MappingProxyType(
        {"win32": "Code.exe", "darwin": "Code", "linux": "code"}
    )

    def installed(self) -> str:
        return (
            ""
            if user_data().exists()
            else f"VS Code does not seem to be installed here (no {user_data()})"
        )

    def targets(self) -> Targets:
        return Targets(files=(models_path(),), rows=((db_path(), (SEALED_ROW,)),))

    def apply(self, current: Capture, ctx: Context) -> Change:
        path = models_path()
        doc = [e for e in _doc(current.file(path), path) if not _ours(e)]
        doc.append(
            {
                "name": "Microtensor",
                "vendor": "customendpoint",
                "apiType": "chat-completions",
                "apiKey": INPUT,
                "models": [
                    {
                        "id": m.id,
                        "name": m.label,
                        "url": f"{ctx.base_url}/v1/chat/completions",
                        "toolCalling": m.tool_calling,
                        "vision": m.vision,
                        "maxInputTokens": m.context or DEFAULT_CONTEXT,
                        "maxOutputTokens": m.max_output or DEFAULT_OUTPUT,
                        "requestHeaders": {TOOL_HEADER: NAME},
                    }
                    for m in ctx.models
                ],
            }
        )
        change = Change()
        change.files[path] = dump_json(doc)
        change.changed = [f"{path}: a Microtensor provider with {len(ctx.models)} models"]
        try:
            sealed, note = encrypt("Code", local_state(), ctx.key)
            change.rows[db_path()] = {SEALED_ROW: buffer_json(sealed)}
            change.changed.append(f"{db_path()}: your key in VS Code's secret storage")
            if note:
                change.notes.append(note)
        except SafeStorageError as exc:
            change.notes.append(
                f"VS Code's secret storage could not be written ({exc}). VS Code asks for the "
                "API key the first time you pick a Microtensor model; paste your key there."
            )
        change.notes.append("Inline suggestions stay on Copilot; Microtensor answers in Chat.")
        return change

    def revert(self, current: Capture, snapshot: Capture) -> Change:
        path = models_path()
        then_raw = snapshot.file(path)
        then = _doc(then_raw, path)
        now = [e for e in _doc(current.file(path), path) if not _ours(e)]
        now.extend(e for e in then if _ours(e))
        change = Change()
        change.files[path] = finish_json(now, then, then_raw, [])
        change.rows[db_path()] = {SEALED_ROW: snapshot.row(db_path(), SEALED_ROW)}
        change.changed = [f"{path}: Microtensor provider removed, your models put back"]
        return change

    def state(self, current: Capture) -> State:
        path = models_path()
        try:
            doc = _doc(current.file(path), path)
        except CliError:
            return State(bridged=False, model="", where=str(path))
        ours = next((e for e in doc if _ours(e)), None)
        model = ""
        if ours and ours.get("models"):
            model = str(ours["models"][0].get("id", ""))
        return State(bridged=ours is not None, model=model, where=str(path))
