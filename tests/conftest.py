from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from microtensor_cli.catalogue import Model, parse_list
from microtensor_cli.config import Credentials

KEY = "mt_sk_test_0123456789abcdef"
BASE = "https://api.example.test"

GENERAL = {
    "id": "glm-4.6-awq",
    "kind": "general",
    "title": "GLM 4.6",
    "context": 131072,
    "max_output": 16384,
    "tool_calling": True,
    "modalities": ["text"],
    "prices": {"usd_in_per_mtok": 0.35, "usd_out_per_mtok": 1.4},
    "capacity": {"operators": 2, "live": True},
}
LONG = {
    **GENERAL,
    "id": "kimi-k3",
    "title": "Kimi K3",
    "context": 1040000,
    "modalities": ["text", "image"],
}
CERTIFIED = {"id": "mt/sql_gen_s1", "kind": "certified", "title": "SQL", "capacity": {"live": True}}
AUTO = {"id": "mt/auto", "capacity": {"live": True}}


class FakeApi:
    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self.entries = entries if entries is not None else [AUTO, CERTIFIED, GENERAL, LONG]
        self.registered: list[tuple[str, str]] = []
        self.unregistered: list[str] = []

    def models(self) -> list[Model]:
        return parse_list({"data": self.entries})

    def register(self, tool: str, model: str, machine: str) -> bool:
        self.registered.append((tool, model))
        return True

    def unregister(self, tool: str, machine: str) -> bool:
        self.unregistered.append(tool)
        return True

    def bridges(self) -> list[dict[str, Any]] | None:
        return [
            {"tool": t, "model": m, "last_request_at": "2026-10-16T10:00:00Z", "requests_30d": 3}
            for t, m in self.registered
        ]


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    user = tmp_path / "user"
    user.mkdir()
    monkeypatch.setenv("MTENSOR_HOME", str(tmp_path / "mtensor"))
    monkeypatch.setenv("MTENSOR_USER_HOME", str(user))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user / ".config"))
    monkeypatch.setenv("APPDATA", str(user / "AppData"))
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "MICROTENSOR_API_KEY", "MTENSOR_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("microtensor_cli.bridge.service.running", lambda processes: False)
    monkeypatch.setattr(
        "microtensor_cli.bridge.harnesses.cursor.encrypt",
        lambda app, state, key: (b"v10sealed", ""),
    )
    monkeypatch.setattr(
        "microtensor_cli.bridge.harnesses.vscode.encrypt",
        lambda app, state, key: (b"v10sealed", ""),
    )
    return user


@pytest.fixture
def credentials() -> Credentials:
    return Credentials(key=KEY, base_url=BASE, source="test")
