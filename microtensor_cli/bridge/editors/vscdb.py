from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path

from microtensor_cli.errors import CliError

TABLE = "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)"


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def read_rows(db: Path, keys: Sequence[str]) -> dict[str, str | None]:
    found: dict[str, str | None] = dict.fromkeys(keys)
    if not db.exists():
        return found
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            for key in keys:
                row = conn.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
                found[key] = _text(row[0]) if row else None
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return found
        raise CliError(f"could not read {db} ({exc})") from exc
    return found


def write_rows(db: Path, rows: Mapping[str, str | None]) -> None:
    if not rows:
        return
    db.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(db, timeout=5)) as conn:
            conn.execute(TABLE)
            for key, value in rows.items():
                if value is None:
                    conn.execute("DELETE FROM ItemTable WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", (key, value)
                    )
            conn.commit()
    except sqlite3.OperationalError as exc:
        raise CliError(f"could not write {db} ({exc}); quit the editor and try again") from exc
