from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.webui.routers import amadeus_bridge
from src.webui.routers.websocket import unified
from src.webui.services.amadeus_bridge import AmadeusBridgeTokenManager


def test_bridge_token_is_independent_and_rotatable(tmp_path: Path) -> None:
    manager = AmadeusBridgeTokenManager(tmp_path / "bridge.json")
    first = manager.get_token()
    second = manager.rotate_token()

    assert len(first) == 64
    assert first != second
    assert manager.verify(first) is False
    assert manager.verify(second) is True


def test_bridge_status_requires_independent_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = AmadeusBridgeTokenManager(tmp_path / "bridge.json")
    token = manager.get_token()
    monkeypatch.setattr(amadeus_bridge, "get_amadeus_bridge_token_manager", lambda: manager)
    app = FastAPI()
    app.include_router(amadeus_bridge.router)

    with TestClient(app) as client:
        denied = client.get("/amadeus/bridge/status")
        allowed = client.get("/amadeus/bridge/status", headers={"X-Amadeus-Token": token})

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["online"] is True


@pytest.mark.asyncio
async def test_amadeus_websocket_scope_cannot_subscribe_to_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    send_response = AsyncMock()
    monkeypatch.setattr(unified.websocket_manager, "send_response", send_response)

    await unified.handle_client_message(
        "connection-id",
        {"op": "subscribe", "id": "request-id", "domain": "logs", "topic": "main"},
        amadeus_only=True,
    )

    send_response.assert_awaited_once()
    assert send_response.await_args.kwargs["error"]["code"] == "amadeus_scope_denied"


@pytest.mark.asyncio
async def test_amadeus_websocket_scope_can_subscribe_to_mind_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscribe = AsyncMock()
    monkeypatch.setattr(unified, "_handle_subscribe", subscribe)
    message = {
        "op": "subscribe",
        "id": "request-id",
        "domain": "maisaka_monitor",
        "topic": "main",
    }

    await unified.handle_client_message("connection-id", message, amadeus_only=True)

    subscribe.assert_awaited_once_with("connection-id", message)
