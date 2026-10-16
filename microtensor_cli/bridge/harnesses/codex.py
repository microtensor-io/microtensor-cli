from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.toml_document import TOMLDocument

from microtensor_cli.bridge.base import TOOL_HEADER, Capture, Change, Context, State, Targets
from microtensor_cli.config import user_home
from microtensor_cli.errors import CliError

NAME = "codex"
PROVIDER = "microtensor"
TOP_KEYS = ("model_provider", "model")


def config_path() -> Path:
    found = os.environ.get("CODEX_HOME")
    root = Path(found) if found else user_home() / ".codex"
    return root / "config.toml"


def _doc(raw: bytes | None, path: Path) -> TOMLDocument:
    try:
        return tomlkit.parse((raw or b"").decode("utf-8-sig"))
    except (UnicodeDecodeError, TOMLKitError) as exc:
        raise CliError(f"{path} is not valid TOML ({exc}), so it was left untouched") from exc


def _plain(doc: TOMLDocument) -> dict[str, Any]:
    return dict(doc.unwrap())


class Codex:
    name = NAME
    title = "Codex"
    after = (
        "Restart Codex to use it. Resume older sessions with: "
        "codex resume <id> -c model_provider=microtensor"
    )
    processes: Mapping[str, str] = MappingProxyType({})

    def installed(self) -> str:
        return ""

    def targets(self) -> Targets:
        return Targets(files=(config_path(),))

    def apply(self, current: Capture, ctx: Context) -> Change:
        path = config_path()
        doc = _doc(current.file(path), path)
        doc["model_provider"] = PROVIDER
        doc["model"] = ctx.model.id
        providers = doc.get("model_providers")
        if providers is None:
            providers = tomlkit.table(is_super_table=True)
            doc["model_providers"] = providers
        entry = tomlkit.table()
        entry["name"] = "Microtensor"
        entry["base_url"] = f"{ctx.base_url}/v1"
        entry["wire_api"] = "responses"
        headers = tomlkit.inline_table()
        headers["x-api-key"] = ctx.key
        headers[TOOL_HEADER] = NAME
        entry["http_headers"] = headers
        providers[PROVIDER] = entry
        change = Change()
        change.files[path] = tomlkit.dumps(doc).encode("utf-8")
        change.private.add(path)
        change.changed = [
            f"{path}: model_provider = {PROVIDER}, model = {ctx.model.id}",
            f"{path}: [model_providers.{PROVIDER}] with the Responses API and your key",
        ]
        return change

    def revert(self, current: Capture, snapshot: Capture) -> Change:
        path = config_path()
        then_raw = snapshot.file(path)
        then = _doc(then_raw, path)
        now = _doc(current.file(path), path)
        for key in TOP_KEYS:
            if key in then:
                now[key] = copy.deepcopy(then[key])
            elif key in now:
                del now[key]
        then_providers = then.get("model_providers")
        now_providers = now.get("model_providers")
        if now_providers is not None:
            if then_providers is not None and PROVIDER in then_providers:
                now_providers[PROVIDER] = copy.deepcopy(then_providers[PROVIDER])
            elif PROVIDER in now_providers:
                del now_providers[PROVIDER]
            if not now_providers and then_providers is None:
                del now["model_providers"]
        change = Change()
        if _plain(now) == _plain(then):
            change.files[path] = then_raw
        elif then_raw is None and not _plain(now):
            change.files[path] = None
        else:
            change.files[path] = tomlkit.dumps(now).encode("utf-8")
        change.changed = [f"{path}: Microtensor provider removed, your earlier values put back"]
        return change

    def state(self, current: Capture) -> State:
        path = config_path()
        try:
            doc = _doc(current.file(path), path)
        except CliError:
            return State(bridged=False, model="", where=str(path))
        bridged = doc.get("model_provider") == PROVIDER
        return State(
            bridged=bridged, model=str(doc.get("model", "")) if bridged else "", where=str(path)
        )
