from pathlib import Path

import httpx
import pytest

from src.amadeus.remote import RemoteMaiBotClient
from src.amadeus.settings import AmadeusSettings


def test_remote_token_is_persisted_but_not_generated_implicitly(tmp_path: Path) -> None:
    settings = AmadeusSettings(tmp_path)

    assert settings.load()["remote_token"] == ""

    settings.update_remote("https://example.test/", "a" * 64, "owner-person")

    assert settings.load() == {
        "remote_base_url": "https://example.test",
        "remote_token": "a" * 64,
        "owner_person_id": "owner-person",
    }


@pytest.mark.asyncio
async def test_remote_client_uses_independent_amadeus_header(tmp_path: Path) -> None:
    settings = AmadeusSettings(tmp_path)
    settings.update_remote("https://example.test", "b" * 64, "owner-person")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Amadeus-Token"] == "b" * 64
        return httpx.Response(200, json={"online": True, "service": "maibot"})

    client = RemoteMaiBotClient(settings, transport=httpx.MockTransport(handler))

    status = await client.get_status()

    assert status["configured"] is True
    assert status["online"] is True


@pytest.mark.asyncio
async def test_remote_client_reports_offline_instead_of_claiming_success(tmp_path: Path) -> None:
    settings = AmadeusSettings(tmp_path)
    client = RemoteMaiBotClient(settings)

    status = await client.get_status()

    assert status == {
        "configured": False,
        "online": False,
        "reason": "尚未配置云端地址或独立 token",
    }
