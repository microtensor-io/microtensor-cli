from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from microtensor_cli.api import Api
from microtensor_cli.bridge import snapshot
from microtensor_cli.bridge.base import Context, Harness
from microtensor_cli.bridge.editors.running import running
from microtensor_cli.bridge.harnesses import HARNESSES
from microtensor_cli.catalogue import AUTO, Model, find, general, offered
from microtensor_cli.config import Credentials, machine_id, masked
from microtensor_cli.errors import CliError

Say = Callable[[str], None]
RUNNING = (
    "{title} is running. Quit it first so it does not overwrite the change when it exits, "
    "then run the command again (or pass --force)."
)
NO_GENERAL = (
    "No general model is served yet, so {title} would get an error on every request. "
    "Run `mtensor models` to see what is served, or pass --force to write the settings anyway."
)


def harness(name: str) -> Harness:
    found = HARNESSES.get(name)
    if found is None:
        raise CliError(f"unknown tool {name}; choose one of {', '.join(HARNESSES)}")
    return found


def _quit_check(h: Harness, force: bool) -> None:
    if h.processes and not force and running(h.processes):
        raise CliError(RUNNING.format(title=h.title))


def choose(
    models: Sequence[Model], wanted: str, title: str, force: bool
) -> tuple[Model, list[Model]]:
    menu = offered(models)
    if not general(models) and not force:
        raise CliError(NO_GENERAL.format(title=title))
    chosen = find(menu, wanted or AUTO) or find(models, wanted)
    if chosen is None:
        names = ", ".join(m.id for m in menu)
        raise CliError(f"{wanted} is not served; choose one of {names}")
    return chosen, menu


def bridge(
    name: str,
    *,
    credentials: Credentials,
    api: Api,
    model: str,
    dry_run: bool,
    force: bool,
    say: Say,
) -> None:
    h = harness(name)
    missing = h.installed()
    if missing:
        raise CliError(missing)
    _quit_check(h, force or dry_run)
    chosen, menu = choose(api.models(), model, h.title, force)
    current = snapshot.capture(h.targets())
    ctx = Context(
        key=credentials.key, base_url=credentials.base_url, model=chosen, models=tuple(menu)
    )
    change = h.apply(current, ctx)
    if dry_run:
        say(f"Dry run: nothing was written. Bridging {h.title} would change:")
        for line in change.changed:
            say(f"  {line}")
        for note in change.notes:
            say(f"Note: {note}")
        return
    held, fresh = snapshot.take(name, current)
    snapshot.write(change)
    registered = api.register(name, chosen.id, machine_id())
    say(f"Bridged {h.title} to Microtensor.")
    say(f"  Model     {chosen.id}")
    say(f"  Key       {masked(credentials.key)}")
    for line in change.changed:
        say(f"  Changed   {line}")
    say(f"  Snapshot  {held}" + ("" if fresh else " (kept from the first bridge)"))
    if not registered:
        say("  Usage     per tool usage appears in the console once the service records bridges")
    for note in change.notes:
        say(f"Note: {note}")
    say(h.after)
    say(f"Undo with: mtensor bridge off {name}")


def off(name: str, *, api: Api | None, force: bool, say: Say) -> None:
    h = harness(name)
    held = snapshot.load(name)
    current = snapshot.capture(h.targets())
    if held is None:
        if h.state(current).bridged:
            raise CliError(
                f"{h.title} looks bridged but no snapshot was saved on this machine; "
                f"edit {h.state(current).where} by hand"
            )
        say(f"{h.title} is not bridged.")
        return
    _quit_check(h, force)
    change = h.revert(current, held)
    snapshot.write(change)
    snapshot.drop(name)
    if api is not None:
        api.unregister(name, machine_id())
    say(f"{h.title} is back on its own settings.")
    for line in change.changed:
        say(f"  {line}")
    say(h.after.replace("to use it", "to pick up the change"))


def restore(*, api: Api | None, force: bool, say: Say) -> None:
    tools = snapshot.saved()
    if not tools:
        say("No snapshot is saved, so there is nothing to restore.")
        return
    for name in tools:
        h = harness(name)
        if h.processes and not force and running(h.processes):
            say(f"Skipped {h.title}: it is running. Quit it and run mtensor bridge restore again.")
            continue
        held = snapshot.load(name)
        if held is None:
            continue
        snapshot.write(snapshot.restore_exact(held))
        snapshot.drop(name)
        if api is not None:
            api.unregister(name, machine_id())
        say(f"Restored {h.title} exactly as it was before the first bridge.")


@dataclass(frozen=True, slots=True)
class Row:
    tool: str
    title: str
    bridged: bool
    model: str
    where: str
    snapshot: bool
    last_seen: str
    requests: int | None

    def view(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "title": self.title,
            "bridged": self.bridged,
            "model": self.model,
            "config": self.where,
            "snapshot": self.snapshot,
            "last_seen_at": self.last_seen,
            "requests_30d": self.requests,
        }


def status(*, api: Api | None) -> list[Row]:
    remote = api.bridges() if api is not None else None
    by_tool = {str(r.get("tool")): r for r in remote or []}
    saved = set(snapshot.saved())
    rows: list[Row] = []
    for name, h in HARNESSES.items():
        state = h.state(snapshot.capture(h.targets()))
        server = by_tool.get(name, {})
        requests = server.get("requests_30d")
        rows.append(
            Row(
                tool=name,
                title=h.title,
                bridged=state.bridged,
                model=state.model,
                where=state.where,
                snapshot=name in saved,
                last_seen=str(server.get("last_seen_at") or ""),
                requests=int(requests) if isinstance(requests, int) else None,
            )
        )
    return rows
