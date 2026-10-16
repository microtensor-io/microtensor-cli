# microtensor-cli

The `mtensor` command for Microtensor customers. Its first job is **Microtensor Bridge**: one command points a coding tool you already use at Microtensor models, and one command puts it back.

## Install

    uv tool install microtensor-cli

or

    pipx install microtensor-cli

Python 3.10 or newer.

## Sign in

Create a key at https://www.microtensor.cloud/console/keys, then:

    mtensor login

The key is saved in `~/.mtensor/credentials.json`, readable only by you. `MICROTENSOR_API_KEY` in the environment works too.

## Bridge a tool

    mtensor bridge claude-code
    mtensor bridge codex
    mtensor bridge opencode
    mtensor bridge cursor
    mtensor bridge vscode

Options for every tool:

| Option | What it does |
|---|---|
| `--model <id>` | The model to use. Default `mt/auto`, which picks a model for each request. `mtensor models` lists the choices. |
| `--key <mt_sk_...>` | Use a different key, for example one key per tool so usage is split by key. |
| `--dry-run` | Print what would change and write nothing. |
| `--force` | Write even when the tool is running, or when no general model is served yet. |

Before the first change, Bridge saves a snapshot of everything it is about to touch in `~/.mtensor/bridge/<tool>/snapshot.json`.

## What each tool gets

| Tool | File it edits | What changes |
|---|---|---|
| Claude Code | `~/.claude/settings.json` | `env.ANTHROPIC_BASE_URL`, `env.ANTHROPIC_AUTH_TOKEN`, a tool header, the model and every model tier, and a model picker of Microtensor models. Start a new session afterwards. |
| Codex | `~/.codex/config.toml` | A `[model_providers.microtensor]` table using the Responses API, `model_provider` and `model`. Restart Codex afterwards. |
| OpenCode | `~/.config/opencode/opencode.json` | A `provider.microtensor` block with the models and `model`. Restart OpenCode afterwards. |
| Cursor | Cursor's `state.vscdb` | The OpenAI base URL override, your key in Cursor's own encrypted store, and the Microtensor models. Quit Cursor first. |
| VS Code | `chatLanguageModels.json` and VS Code's `state.vscdb` | A custom endpoint provider with the Microtensor models, and your key in VS Code's secret storage. Quit VS Code first. |

Limits worth knowing:

- Claude Code sends every request to Microtensor while bridged, background tasks included, so every tier points at the chosen model.
- Cursor routes custom key requests through its own servers, uses them for chat only, and some agent features refuse custom keys. Tab completion stays on Cursor.
- VS Code uses Microtensor in Chat; inline suggestions stay on Copilot.
- On Linux, Cursor and VS Code keys are stored the way those editors store them without a keyring: obfuscated, not encrypted.

## Check and undo

    mtensor bridge status
    mtensor bridge off claude-code
    mtensor bridge restore

- `status` shows each tool, whether it is bridged and to which model, and its requests once the service records them.
- `off <tool>` removes what Bridge added and puts back the values you had before, keeping any other change you made since.
- `restore` writes every saved snapshot back exactly as it was before the first bridge.

## Models

    mtensor models

Lists what Microtensor serves: general models, which coding tools need, and certified specialists, which answer one task each. Until a general model is served, `mtensor bridge` refuses and says so, because the tool would get an error on every request; `--force` writes the settings anyway.

## Development

    pip install -e ".[dev]"
    ruff check . && mypy microtensor_cli && pytest -q

Docs: https://www.microtensor.cloud/docs/api/getting-started/bridge
