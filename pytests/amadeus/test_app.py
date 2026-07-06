from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from src.amadeus.app import StatusMonitor, create_app
from src.amadeus.storage import AmadeusStore


class FakeRemoteClient:
    async def get_status(self) -> Dict[str, Any]:
        return {"configured": True, "online": True, "service": "maibot"}

    async def get_identity(self) -> Dict[str, Any]:
        return {"configured": True, "mapped": True, "display_name": "主人"}


class FakeTtsService:
    def status(self) -> Dict[str, Any]:
        return {"state": "stopped", "running": False, "managed": False}

    def start(self) -> Dict[str, Any]:
        return {"state": "starting", "running": False, "managed": False}

    def stop(self) -> Dict[str, Any]:
        return self.status()


class OfflineRemoteClient(FakeRemoteClient):
    async def get_status(self) -> Dict[str, Any]:
        return {"configured": True, "online": False, "reason": "connection refused"}


def test_status_aggregates_remote_identity_and_local_services(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        remote_client=FakeRemoteClient(),  # type: ignore[arg-type]
        tts_service=FakeTtsService(),  # type: ignore[arg-type]
        start_monitor=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["remote"]["online"] is True
    assert response.json()["identity"]["mapped"] is True
    assert response.json()["local"]["tts"]["state"] == "stopped"


def test_sensitive_command_requires_explicit_decision(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        remote_client=FakeRemoteClient(),  # type: ignore[arg-type]
        tts_service=FakeTtsService(),  # type: ignore[arg-type]
        start_monitor=False,
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/commands",
            json={"action": "file.modify", "payload": {"path": "notes.txt"}},
        )
        command = created.json()
        decided = client.post(
            f"/api/commands/{command['id']}/decision",
            json={"approved": True, "reason": "允许本次修改"},
        )

    assert created.status_code == 200
    assert command["status"] == "pending_approval"
    assert decided.json()["status"] == "approved"


def test_remote_configuration_never_echoes_token(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        remote_client=FakeRemoteClient(),  # type: ignore[arg-type]
        tts_service=FakeTtsService(),  # type: ignore[arg-type]
        start_monitor=False,
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/config/remote",
            json={
                "remote_base_url": "https://example.test/",
                "remote_token": "c" * 64,
                "owner_person_id": "owner-person",
            },
        )
        loaded = client.get("/api/config/remote")

    assert response.status_code == 200
    assert "remote_token" not in response.json()
    assert loaded.json()["remote_token_configured"] is True


def test_remote_configuration_rejects_blank_owner_mapping(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        remote_client=FakeRemoteClient(),  # type: ignore[arg-type]
        tts_service=FakeTtsService(),  # type: ignore[arg-type]
        start_monitor=False,
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/config/remote",
            json={
                "remote_base_url": "https://example.test",
                "remote_token": "d" * 64,
                "owner_person_id": "   ",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_monitor_reports_initial_configured_offline_state(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)
    monitor = StatusMonitor(OfflineRemoteClient(), store, interval_seconds=1)

    await monitor.check_once()

    events = store.list_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "service.offline"
