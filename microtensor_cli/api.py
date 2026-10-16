from __future__ import annotations

import platform
from typing import Any

import httpx

from microtensor_cli import __version__
from microtensor_cli.catalogue import Model, parse_list
from microtensor_cli.config import CONSOLE_KEYS_URL, Credentials
from microtensor_cli.errors import CliError

TIMEOUT = 20.0
REFUSED = (
    "the key was refused by {base}; create one at " + CONSOLE_KEYS_URL + " and run: mtensor login"
)


class Api:
    def __init__(self, credentials: Credentials, *, client: httpx.Client | None = None) -> None:
        self.credentials = credentials
        self._client = client or httpx.Client(timeout=TIMEOUT)

    def _headers(self, tool: str = "") -> dict[str, str]:
        found = {
            "authorization": f"Bearer {self.credentials.key}",
            "accept": "application/json",
            "user-agent": f"mtensor/{__version__} ({platform.system().lower()})",
        }
        if tool:
            found["x-microtensor-tool"] = tool
        return found

    def _url(self, path: str) -> str:
        return f"{self.credentials.base_url}{path}"

    def _send(self, method: str, path: str, *, tool: str = "", body: Any = None) -> httpx.Response:
        try:
            return self._client.request(
                method, self._url(path), headers=self._headers(tool), json=body
            )
        except httpx.HTTPError as exc:
            raise CliError(
                f"could not reach {self.credentials.base_url} ({exc.__class__.__name__})"
            ) from exc

    def _refused(self, answer: httpx.Response) -> None:
        if answer.status_code in (401, 403):
            raise CliError(REFUSED.format(base=self.credentials.base_url))

    def models(self) -> list[Model]:
        answer = self._send("GET", "/v1/models")
        self._refused(answer)
        if answer.status_code != 200:
            raise CliError(f"listing models failed with {answer.status_code}")
        return parse_list(answer.json())

    def register(self, tool: str, model: str, machine: str) -> bool:
        body = {
            "tool": tool,
            "model": model,
            "host": machine,
            "os": platform.system().lower(),
            "client": f"mtensor/{__version__}",
        }
        try:
            answer = self._send("POST", "/v1/bridge/tools", tool=tool, body=body)
        except CliError:
            return False
        return answer.status_code in (200, 201)

    def unregister(self, tool: str, machine: str) -> bool:
        try:
            answer = self._send("DELETE", f"/v1/bridge/tools/{tool}?host={machine}", tool=tool)
        except CliError:
            return False
        return answer.status_code in (200, 204)

    def bridges(self) -> list[dict[str, Any]] | None:
        try:
            answer = self._send("GET", "/v1/bridge/tools")
        except CliError:
            return None
        if answer.status_code != 200:
            return None
        found = answer.json().get("tools")
        return [dict(t) for t in found] if isinstance(found, list) else None
