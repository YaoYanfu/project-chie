from pathlib import Path

from src.amadeus.storage import AmadeusStore


def test_event_can_be_listed_and_deleted(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)
    event = store.add_event("remote.maibot", "service.offline", "云端千惠已离线", status="warning")

    assert store.list_events() == [event]
    assert store.delete_event(event["id"]) is True
    assert store.list_events() == []


def test_free_action_is_accepted_without_approval(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)

    command = store.create_command("message.send", {"content": "你好"})

    assert command["status"] == "accepted"
    assert store.decide_command(command["id"], approved=True) is None


def test_sensitive_action_stays_pending_until_decided(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)
    command = store.create_command("command.run", {"command": "whoami"})

    assert command["status"] == "pending_approval"

    decided = store.decide_command(command["id"], approved=False, reason="不需要执行")

    assert decided is not None
    assert decided["status"] == "rejected"
    assert decided["decision_reason"] == "不需要执行"


def test_unknown_action_is_rejected_without_default_fallback(tmp_path: Path) -> None:
    store = AmadeusStore(tmp_path)

    try:
        store.create_command("unknown.action", {})
    except ValueError as exc:
        assert "未定义权限策略" in str(exc)
    else:
        raise AssertionError("未知动作不应被接受")
