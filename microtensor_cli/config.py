from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from microtensor_cli.files import atomic_write, read_bytes, remove

DEFAULT_BASE_URL = "https://api.microtensor.cloud"
CONSOLE_KEYS_URL = "https://www.microtensor.cloud/console/keys"
ENV_HOME = "MTENSOR_HOME"
ENV_USER_HOME = "MTENSOR_USER_HOME"
ENV_KEY = "MICROTENSOR_API_KEY"
ENV_BASE = "MTENSOR_BASE_URL"
KEY_PREFIX = "mt_sk_"


@dataclass(frozen=True, slots=True)
class Credentials:
    key: str
    base_url: str
    source: str


def home() -> Path:
    found = os.environ.get(ENV_HOME)
    return Path(found) if found else Path.home() / ".mtensor"


def user_home() -> Path:
    found = os.environ.get(ENV_USER_HOME)
    return Path(found) if found else Path.home()


def app_data() -> Path:
    if sys.platform == "win32":
        found = os.environ.get("APPDATA")
        return Path(found) if found else user_home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return user_home() / "Library" / "Application Support"
    found = os.environ.get("XDG_CONFIG_HOME")
    return Path(found) if found else user_home() / ".config"


def xdg_config() -> Path:
    found = os.environ.get("XDG_CONFIG_HOME")
    return Path(found) if found else user_home() / ".config"


def credentials_path() -> Path:
    return home() / "credentials.json"


def normal_base(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    return cleaned[:-3] if cleaned.endswith("/v1") else cleaned


def load_credentials() -> Credentials | None:
    from_env = os.environ.get(ENV_KEY, "").strip()
    base = normal_base(os.environ.get(ENV_BASE, "") or DEFAULT_BASE_URL)
    raw = read_bytes(credentials_path())
    if raw:
        try:
            held = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            held = {}
        if not os.environ.get(ENV_BASE) and held.get("base_url"):
            base = normal_base(str(held["base_url"]))
        if not from_env and held.get("key"):
            return Credentials(key=str(held["key"]), base_url=base, source=str(credentials_path()))
    if from_env:
        return Credentials(key=from_env, base_url=base, source=ENV_KEY)
    return None


def save_credentials(key: str, base_url: str) -> Path:
    path = credentials_path()
    body = {
        "key": key,
        "base_url": normal_base(base_url),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    atomic_write(path, (json.dumps(body, indent=2) + "\n").encode("utf-8"), private=True)
    return path


def clear_credentials() -> bool:
    path = credentials_path()
    existed = path.exists()
    remove(path)
    return existed


def machine_id() -> str:
    path = home() / "machine"
    raw = read_bytes(path)
    if raw and raw.strip():
        return raw.decode("utf-8").strip()
    made = uuid.uuid4().hex[:16]
    atomic_write(path, made.encode("utf-8"), private=True)
    return made


def masked(key: str) -> str:
    if len(key) <= 12:
        return KEY_PREFIX + "..."
    return f"{key[:8]}...{key[-4:]}"
