from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict

from microtensor_cli import __version__
from microtensor_cli.api import Api
from microtensor_cli.bridge import service
from microtensor_cli.bridge.harnesses import HARNESSES
from microtensor_cli.catalogue import context_label
from microtensor_cli.config import (
    CONSOLE_KEYS_URL,
    DEFAULT_BASE_URL,
    ENV_BASE,
    KEY_PREFIX,
    Credentials,
    clear_credentials,
    load_credentials,
    normal_base,
    save_credentials,
)
from microtensor_cli.errors import CliError

SIGN_IN = f"sign in first with: mtensor login (create a key at {CONSOLE_KEYS_URL})"


def say(line: str) -> None:
    print(line)


def _credentials(key: str = "") -> Credentials:
    held = load_credentials()
    if key:
        base = held.base_url if held else normal_base(os.environ.get(ENV_BASE) or DEFAULT_BASE_URL)
        return Credentials(key=key.strip(), base_url=base, source="--key")
    if held is None:
        raise CliError(SIGN_IN)
    return held


def _table(rows: Sequence[Sequence[str]]) -> None:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        say("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


def login(args: argparse.Namespace) -> int:
    key = (args.key or os.environ.get("MICROTENSOR_API_KEY") or "").strip()
    if not key:
        key = getpass.getpass(f"Microtensor API key ({KEY_PREFIX}...): ").strip()
    if not key.startswith(KEY_PREFIX):
        raise CliError(f"that does not look like a Microtensor key; keys start with {KEY_PREFIX}")
    base = normal_base(args.base_url or os.environ.get(ENV_BASE) or DEFAULT_BASE_URL)
    models = Api(Credentials(key=key, base_url=base, source="login")).models()
    path = save_credentials(key, base)
    say(f"Signed in. The key is saved in {path}, readable only by you.")
    say(
        f"{len(models)} models are listed. "
        "Next: mtensor bridge <tool>, for example mtensor bridge claude-code"
    )
    return 0


def logout(_: argparse.Namespace) -> int:
    say("Signed out." if clear_credentials() else "No saved key to remove.")
    return 0


def models(args: argparse.Namespace) -> int:
    found = Api(_credentials()).models()
    if args.json:
        say(json.dumps([asdict(m) for m in found], indent=2))
        return 0
    rows = [["MODEL", "KIND", "CONTEXT", "TOOLS", "PRICE PER 1M (IN/OUT)", "SERVED NOW"]]
    for m in found:
        price = (
            f"${m.usd_in_per_mtok:g} / ${m.usd_out_per_mtok:g}"
            if m.usd_in_per_mtok is not None and m.usd_out_per_mtok is not None
            else "-"
        )
        rows.append(
            [
                m.id,
                m.kind,
                context_label(m.context) if m.context else "-",
                "yes" if m.tool_calling else "no",
                price,
                "yes" if m.live else "no",
            ]
        )
    _table(rows)
    if not any(m.general for m in found):
        say(
            "No general model is served yet; coding tools need one. "
            "Certified specialists answer one task each."
        )
    return 0


def bridge(args: argparse.Namespace) -> int:
    action = args.action
    if action == "status":
        return bridge_status(args)
    if action == "off":
        held = load_credentials()
        service.off(args.tool, api=Api(held) if held else None, force=args.force, say=say)
        return 0
    if action == "restore":
        held = load_credentials()
        service.restore(api=Api(held) if held else None, force=args.force, say=say)
        return 0
    credentials = _credentials(args.key or "")
    service.bridge(
        action,
        credentials=credentials,
        api=Api(credentials),
        model=args.model or "",
        dry_run=args.dry_run,
        force=args.force,
        say=say,
    )
    return 0


def bridge_status(args: argparse.Namespace) -> int:
    held = load_credentials()
    rows = service.status(api=Api(held) if held else None)
    if args.json:
        say(json.dumps([r.view() for r in rows], indent=2))
        return 0
    table = [["TOOL", "STATE", "MODEL", "REQUESTS 30D", "LAST REQUEST", "SETTINGS"]]
    for r in rows:
        table.append(
            [
                r.tool,
                "bridged" if r.bridged else "not bridged",
                r.model or "-",
                "-" if r.requests is None else str(r.requests),
                r.last_seen or "-",
                r.where,
            ]
        )
    _table(table)
    if held is None:
        say(SIGN_IN)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="mtensor",
        description=(
            "Microtensor from the command line. Bridge your coding tools to Microtensor models."
        ),
    )
    root.add_argument("--version", action="version", version=f"mtensor {__version__}")
    commands = root.add_subparsers(dest="command", required=True, metavar="command")

    signin = commands.add_parser("login", help="save an API key for this machine")
    signin.add_argument("--key", help="the key; asked for when left out")
    signin.add_argument("--base-url", help=f"the API host (default {DEFAULT_BASE_URL})")
    signin.set_defaults(run=login)

    signout = commands.add_parser("logout", help="remove the saved key")
    signout.set_defaults(run=logout)

    listing = commands.add_parser("models", help="list the models Microtensor serves")
    listing.add_argument("--json", action="store_true", help="print JSON")
    listing.set_defaults(run=models)

    bridging = commands.add_parser(
        "bridge",
        help="point a coding tool at Microtensor, check it, or undo it",
        description=(
            "Point a coding tool at Microtensor. Each tool's settings are saved first, "
            "so off and restore put them back."
        ),
    )
    actions = bridging.add_subparsers(
        dest="action", required=True, metavar="{tool,status,off,restore}"
    )
    for name, h in HARNESSES.items():
        tool = actions.add_parser(name, help=f"bridge {h.title}")
        tool.add_argument("--model", help="the model to use (default mt/auto)")
        tool.add_argument(
            "--key", help="use this key instead of the saved one, for example a key per tool"
        )
        tool.add_argument(
            "--dry-run", action="store_true", help="show what would change and write nothing"
        )
        tool.add_argument(
            "--force",
            action="store_true",
            help="write even if the tool is running or no general model is served",
        )
    check = actions.add_parser("status", help="which tools are bridged and to which model")
    check.add_argument("--json", action="store_true", help="print JSON")
    undo = actions.add_parser("off", help="put one tool back on its own settings")
    undo.add_argument("tool", choices=list(HARNESSES))
    undo.add_argument("--force", action="store_true", help="write even if the tool is running")
    back = actions.add_parser("restore", help="restore every tool from its saved snapshot")
    back.add_argument("--force", action="store_true", help="write even if a tool is running")
    bridging.set_defaults(run=bridge)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        code: int = args.run(args)
        return code
    except CliError as exc:
        print(f"mtensor: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 130
