from __future__ import annotations

from microtensor_cli.bridge.base import Harness
from microtensor_cli.bridge.harnesses.claude_code import ClaudeCode
from microtensor_cli.bridge.harnesses.codex import Codex
from microtensor_cli.bridge.harnesses.cursor import Cursor
from microtensor_cli.bridge.harnesses.opencode import OpenCode
from microtensor_cli.bridge.harnesses.vscode import VSCode

HARNESSES: dict[str, Harness] = {
    h.name: h for h in (ClaudeCode(), Codex(), OpenCode(), Cursor(), VSCode())
}
