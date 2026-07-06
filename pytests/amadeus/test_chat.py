from copy import deepcopy

import pytest

from src.amadeus.chat import build_remote_websocket_url, prepare_client_message


def test_build_remote_websocket_url_keeps_transport_security() -> None:
    assert (
        build_remote_websocket_url("https://example.test")
        == "wss://example.test/api/webui/ws"
    )


def test_build_remote_websocket_url_preserves_reverse_proxy_prefix() -> None:
    assert build_remote_websocket_url("https://example.test/chie") == "wss://example.test/chie/api/webui/ws"


def test_session_open_forces_owner_mapping_and_independent_chat_flow() -> None:
    message = {
        "op": "call",
        "domain": "chat",
        "method": "session.open",
        "session": "desktop",
        "data": {"person_id": "attacker", "group_id": "qq-group"},
    }

    prepared = prepare_client_message(deepcopy(message), "real-owner")

    assert prepared["data"]["person_id"] == "real-owner"
    assert prepared["data"]["platform"] == "amadeus"
    assert prepared["data"]["group_id"] == "amadeus_desktop"


def test_non_chat_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="只允许聊天"):
        prepare_client_message({"op": "subscribe", "domain": "logs"}, "owner")
