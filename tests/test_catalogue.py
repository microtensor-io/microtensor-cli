from __future__ import annotations

import json
from typing import Any

import pytest

from microtensor_cli import app
from microtensor_cli.catalogue import Band, parse
from microtensor_cli.config import Credentials
from tests.conftest import AUTO, GENERAL, FakeApi

TIERED: dict[str, Any] = {
    "id": "mt/tiered",
    "kind": "certified",
    "title": "Tiered",
    "prices": {
        "usd_in_per_mtok": 0.0,
        "usd_out_per_mtok": 0.0,
        "usd_per_request": 0.001,
        "schedule": [
            {"input_tokens_below": 50000, "usd_per_request": 0.001},
            {"usd_per_request": 0.004},
        ],
    },
    "capacity": {"live": True},
}
FLAT: dict[str, Any] = {
    **TIERED,
    "id": "mt/flat",
    "prices": {"usd_in_per_mtok": 0.0, "usd_out_per_mtok": 0.0, "usd_per_request": 0.004},
}
TOKENS = "General model, 128K context, tools, $0.35 in, $1.4 out per 1M tokens"


def test_per_request_prices_are_built_from_the_data() -> None:
    tiered = parse(TIERED)
    assert tiered.schedule == (Band(50000, 0.001), Band(None, 0.004))
    assert tiered.usd_per_request == 0.001
    assert tiered.describe() == "Certified specialist, $0.001 to $0.004 per request"
    assert parse(FLAT).describe() == "Certified specialist, $0.004 per request"
    wire = {**GENERAL, "prices": {**GENERAL["prices"], "usd_per_request": 0.0}}
    assert parse(GENERAL).describe() == TOKENS and parse(wire).describe() == TOKENS


def test_odd_price_content_is_skipped_and_never_raises() -> None:
    odd = [
        None,
        "band",
        ["usd_per_request", 0.001],
        {},
        {"usd_per_request": 0},
        {"usd_per_request": -0.001},
        {"usd_per_request": "free"},
        {"usd_per_request": True},
        {"usd_per_request": float("inf")},
        {"usd_per_request": 10**400},
        {"input_tokens_below": "soon", "usd_per_request": 0.004},
    ]
    kept = parse({**TIERED, "prices": {"usd_per_request": 10**400, "schedule": odd}})
    assert kept.schedule == (Band(None, 0.004),) and kept.usd_per_request is None
    assert kept.describe() == "Certified specialist, $0.004 per request"
    for schedule in ("bands", 7, None, {"usd_per_request": 0.001}, odd[:10]):
        model = parse({**GENERAL, "prices": {**GENERAL["prices"], "schedule": schedule}})
        assert model.schedule == () and model.describe() == TOKENS


def test_models_table_and_json_carry_per_request_prices(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], credentials: Credentials
) -> None:
    served = [AUTO, GENERAL]
    monkeypatch.setattr(app, "_credentials", lambda: credentials)
    monkeypatch.setattr(app, "Api", lambda held: FakeApi(served))
    assert app.main(["models"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "MODEL        KIND     CONTEXT  TOOLS  PRICE PER 1M (IN/OUT)  SERVED NOW",
        "mt/auto      router   -        no     -                      yes",
        "glm-4.6-awq  general  128K     yes    $0.35 / $1.4           yes",
    ]
    served += [TIERED, FLAT]
    assert app.main(["models"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "MODEL        KIND       CONTEXT  TOOLS  PRICE                         SERVED NOW",
        "mt/auto      router     -        no     -                             yes",
        "glm-4.6-awq  general    128K     yes    $0.35 / $1.4 per 1M (in/out)  yes",
        "mt/tiered    certified  -        no     $0.001 to $0.004 per request  yes",
        "mt/flat      certified  -        no     $0.004 per request            yes",
    ]
    assert app.main(["models", "--json"]) == 0
    rows = {row["id"]: row for row in json.loads(capsys.readouterr().out)}
    assert rows["mt/tiered"]["usd_per_request"] == 0.001
    assert rows["mt/tiered"]["schedule"] == [
        {"input_tokens_below": 50000, "usd_per_request": 0.001},
        {"input_tokens_below": None, "usd_per_request": 0.004},
    ]
    assert rows["glm-4.6-awq"]["usd_in_per_mtok"] == 0.35 and rows["glm-4.6-awq"]["live"]
    assert rows["glm-4.6-awq"]["usd_per_request"] is None and rows["glm-4.6-awq"]["schedule"] == []
