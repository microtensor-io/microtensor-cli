from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from microtensor_cli.errors import CliError


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def atomic_write(path: Path, data: bytes, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600 if private else (path.stat().st_mode & 0o777 if path.exists() else None)
    handle, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def load_json(raw: bytes | None, path: Path, *, empty: Any) -> Any:
    if raw is None or not raw.strip():
        return empty
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(
            f"{path} is not plain JSON ({exc.__class__.__name__}), so it was left untouched; "
            "remove comments or trailing commas and run the command again"
        ) from exc


def dump_json(doc: Any) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
