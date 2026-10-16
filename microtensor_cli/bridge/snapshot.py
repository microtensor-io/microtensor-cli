from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from microtensor_cli.bridge.base import Capture, Change, Targets
from microtensor_cli.bridge.editors.vscdb import read_rows, write_rows
from microtensor_cli.config import home
from microtensor_cli.errors import CliError
from microtensor_cli.files import atomic_write, read_bytes, remove


def directory() -> Path:
    return home() / "bridge"


def path_for(tool: str) -> Path:
    return directory() / tool / "snapshot.json"


def capture(targets: Targets) -> Capture:
    found = Capture()
    for path in targets.files:
        found.files[str(path)] = read_bytes(path)
    for db, keys in targets.rows:
        found.rows[str(db)] = read_rows(db, keys)
    return found


def _encode(found: Capture) -> dict[str, Any]:
    return {
        "files": {
            p: None if raw is None else base64.b64encode(raw).decode("ascii")
            for p, raw in found.files.items()
        },
        "rows": found.rows,
    }


def _decode(body: dict[str, Any]) -> Capture:
    files = {
        str(p): None if raw is None else base64.b64decode(str(raw))
        for p, raw in (body.get("files") or {}).items()
    }
    rows = {
        str(db): {str(k): None if v is None else str(v) for k, v in (held or {}).items()}
        for db, held in (body.get("rows") or {}).items()
    }
    return Capture(files=files, rows=rows)


def load(tool: str) -> Capture | None:
    raw = read_bytes(path_for(tool))
    if raw is None:
        return None
    try:
        return _decode(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CliError(f"the snapshot {path_for(tool)} is damaged ({exc})") from exc


def take(tool: str, found: Capture) -> tuple[Path, bool]:
    target = path_for(tool)
    if target.exists():
        return target, False
    body = {
        "tool": tool,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **_encode(found),
    }
    atomic_write(target, (json.dumps(body, indent=2) + "\n").encode("utf-8"), private=True)
    return target, True


def drop(tool: str) -> None:
    target = path_for(tool)
    remove(target)
    try:
        target.parent.rmdir()
    except OSError:
        return


def saved() -> list[str]:
    root = directory()
    if not root.exists():
        return []
    return sorted(p.parent.name for p in root.glob("*/snapshot.json"))


def write(change: Change) -> None:
    for path, data in change.files.items():
        if data is None:
            remove(path)
        else:
            atomic_write(path, data, private=path in change.private)
    for db, rows in change.rows.items():
        write_rows(db, rows)


def restore_exact(found: Capture) -> Change:
    change = Change()
    for name, raw in found.files.items():
        change.files[Path(name)] = raw
    for db, rows in found.rows.items():
        change.rows[Path(db)] = dict(rows)
    return change
