from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import tomlkit

from microtensor_cli.bridge import service, snapshot
from microtensor_cli.bridge.harnesses import claude_code, codex, cursor, opencode, vscode
from microtensor_cli.config import Credentials
from microtensor_cli.errors import CliError
from tests.conftest import AUTO, BASE, CERTIFIED, KEY, FakeApi


def run(name: str, credentials: Credentials, api: FakeApi, **extra: object) -> list[str]:
    lines: list[str] = []
    service.bridge(
        name,
        credentials=credentials,
        api=api,
        model=str(extra.get("model", "")),
        dry_run=bool(extra.get("dry_run", False)),
        force=bool(extra.get("force", False)),
        say=lines.append,
    )
    return lines


def test_claude_code_round_trip(homes: Path, credentials: Credentials) -> None:
    path = claude_code.settings_path()
    path.parent.mkdir(parents=True)
    original = b'{\n  "theme": "dark",\n  "apiKeyHelper": "/bin/key",\n  "env": {"OTHER": "1"}\n}\n'
    path.write_bytes(original)
    api = FakeApi()
    run("claude-code", credentials, api)
    doc = json.loads(path.read_text())
    assert doc["theme"] == "dark" and doc["env"]["OTHER"] == "1" and "apiKeyHelper" not in doc
    assert doc["env"]["ANTHROPIC_BASE_URL"] == BASE and doc["env"]["ANTHROPIC_AUTH_TOKEN"] == KEY
    assert (
        doc["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "mt/auto[1m]"
        and doc["model"] == "mt/auto[1m]"
    )
    picker = [o["model"] for o in doc["modelPicker"]["options"]]
    assert picker == ["mt/auto[1m]", "glm-4.6-awq", "kimi-k3[1m]"]
    assert api.registered == [("claude-code", "mt/auto")]
    rows = {r.tool: r for r in service.status(api=api)}
    assert rows["claude-code"].bridged and rows["claude-code"].model == "mt/auto"
    assert rows["claude-code"].requests == 3 and not rows["codex"].bridged
    service.off("claude-code", api=api, force=False, say=lambda _: None)
    assert path.read_bytes() == original
    assert snapshot.saved() == [] and api.unregistered == ["claude-code"]


def test_codex_keeps_other_tables_and_restores_bytes(homes: Path, credentials: Credentials) -> None:
    path = codex.config_path()
    path.parent.mkdir(parents=True)
    original = b'model = "gpt-5"\n\n[mcp_servers.docs]\ncommand = "npx"\nargs = ["docs-mcp"]\n'
    path.write_bytes(original)
    run("codex", credentials, FakeApi(), model="glm-4.6-awq")
    doc = tomlkit.parse(path.read_text()).unwrap()
    assert doc["model_provider"] == "microtensor" and doc["model"] == "glm-4.6-awq"
    provider = doc["model_providers"]["microtensor"]
    assert provider["base_url"] == f"{BASE}/v1" and provider["wire_api"] == "responses"
    assert provider["http_headers"] == {"x-api-key": KEY, "X-Microtensor-Tool": "codex"}
    assert doc["mcp_servers"]["docs"]["command"] == "npx"
    service.off("codex", api=None, force=False, say=lambda _: None)
    assert path.read_bytes() == original


def test_opencode_new_file_is_removed_on_off_and_restore_is_exact(
    homes: Path, credentials: Credentials
) -> None:
    path = opencode.config_path()
    run("opencode", credentials, FakeApi())
    doc = json.loads(path.read_text())
    assert doc["model"] == "microtensor/mt/auto"
    assert doc["provider"]["microtensor"]["options"]["baseURL"] == f"{BASE}/v1"
    assert doc["provider"]["microtensor"]["models"]["kimi-k3"]["modalities"]["input"] == [
        "text",
        "image",
    ]
    service.off("opencode", api=None, force=False, say=lambda _: None)
    assert not path.exists()
    claude = claude_code.settings_path()
    run("claude-code", credentials, FakeApi())
    claude.write_text(claude.read_text().replace('"model"', '"theme": "light", "model"'))
    service.restore(api=None, force=False, say=lambda _: None)
    assert not claude.exists() and snapshot.saved() == []


def test_editors_write_rows_and_put_them_back(homes: Path, credentials: Credentials) -> None:
    db = cursor.db_path()
    db.parent.mkdir(parents=True)
    blob = {
        "aiSettings": {
            "userAddedModels": ["gpt-x"],
            "modelConfig": {"composer": {"modelName": "gpt-x"}},
        }
    }
    original = json.dumps(blob, separators=(",", ":"))
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        conn.execute("INSERT INTO ItemTable VALUES (?, ?)", (cursor.APP_KEY, original))
        conn.commit()
    run("cursor", credentials, FakeApi())
    rows = snapshot.capture(cursor.Cursor().targets()).rows[str(db)]
    now = json.loads(rows[cursor.APP_KEY] or "{}")
    assert now["openAIBaseUrl"] == f"{BASE}/v1" and now["useOpenAIKey"] is True
    assert now["aiSettings"]["userAddedModels"] == ["gpt-x", "mt/auto", "glm-4.6-awq", "kimi-k3"]
    assert now["aiSettings"]["modelConfig"]["composer"]["modelName"] == "mt/auto"
    assert json.loads(rows[cursor.SEALED_ROW] or "{}")["data"][:3] == list(b"v10")
    service.off("cursor", api=None, force=False, say=lambda _: None)
    back = snapshot.capture(cursor.Cursor().targets()).rows[str(db)]
    assert back[cursor.APP_KEY] == original and back[cursor.SEALED_ROW] is None

    models = vscode.models_path()
    models.parent.mkdir(parents=True)
    mine = [{"name": "Mine", "vendor": "customendpoint", "apiKey": "${input:mine}", "models": []}]
    models.write_text(json.dumps(mine))
    before = models.read_bytes()
    run("vscode", credentials, FakeApi())
    providers = json.loads(models.read_text())
    assert [p["name"] for p in providers] == ["Mine", "Microtensor"]
    assert providers[1]["models"][0]["url"] == f"{BASE}/v1/chat/completions"
    service.off("vscode", api=None, force=False, say=lambda _: None)
    assert models.read_bytes() == before


def test_refuses_without_a_general_model_unless_forced(
    homes: Path, credentials: Credentials
) -> None:
    api = FakeApi([AUTO, CERTIFIED])
    with pytest.raises(CliError, match="No general model is served yet"):
        run("claude-code", credentials, api)
    assert not claude_code.settings_path().exists()
    lines = run("claude-code", credentials, api, dry_run=True, force=True)
    assert lines[0].startswith("Dry run") and not claude_code.settings_path().exists()
    with pytest.raises(CliError, match="not served"):
        run("claude-code", credentials, FakeApi(), model="nope")
