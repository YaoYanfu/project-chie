from copy import deepcopy
from pathlib import Path

import pytest

from src.amadeus.chat import ChatRelay, build_remote_websocket_url, prepare_client_message
from src.amadeus.settings import AmadeusSettings
from src.amadeus.storage import AmadeusStore


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


def test_remote_history_is_persisted_without_duplicates(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)
    relay = ChatRelay(AmadeusSettings(tmp_path), store)
    payload = {
        "op": "event",
        "domain": "chat",
        "data": {
            "type": "history",
            "messages": [
                {
                    "id": "user-1",
                    "type": "user",
                    "content": "你好",
                    "timestamp": 10,
                    "is_bot": False,
                },
                {
                    "id": "bot-1",
                    "type": "bot",
                    "content": "我在",
                    "timestamp": 20,
                    "is_bot": True,
                },
            ],
        },
    }

    relay._record_remote_event(payload)
    relay._record_remote_event(payload)

    messages = store.list_chat_messages()
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "你好"),
        ("assistant", "我在"),
    ]


def test_non_chat_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="只允许聊天"):
        prepare_client_message({"op": "subscribe", "domain": "logs"}, "owner")
