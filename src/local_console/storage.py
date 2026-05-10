"""本地控制台会话存储。"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Literal, Set
from uuid import uuid4

import hashlib
import json
import re

MessageRole = Literal["user", "assistant", "system"]

_SESSION_ID_PATTERN = re.compile("[^a-zA-Z0-9_.\\-\u3040-\u30ff\u3400-\u9fff]+")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_session_id(session_id: str) -> str:
    normalized = _SESSION_ID_PATTERN.sub("_", session_id.strip())
    normalized = normalized.strip("._-")
    return normalized or "default"


def _build_legacy_message_id(role: str, content: str, created_at: str, source: str) -> str:
    raw_value = f"{role}\n{created_at}\n{source}\n{content}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:20]
    return f"legacy-{digest}"


@dataclass(slots=True)
class ChatMessage:
    """本地控制台的一条聊天消息。"""

    message_id: str
    role: MessageRole
    content: str
    created_at: str
    source: str = "local_console"

    @classmethod
    def create(cls, role: MessageRole, content: str, source: str = "local_console") -> "ChatMessage":
        return cls(message_id=uuid4().hex, role=role, content=content, created_at=_utc_now_text(), source=source)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ChatMessage":
        role = payload.get("role", "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        content = str(payload.get("content", ""))
        created_at = str(payload.get("created_at") or _utc_now_text())
        source = str(payload.get("source") or "local_console")
        message_id = str(payload.get("message_id") or _build_legacy_message_id(role, content, created_at, source))
        return cls(
            message_id=message_id,
            role=role,
            content=content,
            created_at=created_at,
            source=source,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConversationStore:
    """基于 JSON 文件的轻量会话存储。"""

    def __init__(self, data_dir: Path):
        self._session_dir = data_dir / "sessions"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _session_path(self, session_id: str) -> Path:
        safe_session_id = normalize_session_id(session_id)
        return self._session_dir / f"{safe_session_id}.json"

    def load_messages(self, session_id: str) -> List[ChatMessage]:
        path = self._session_path(session_id)
        with self._lock:
            if not path.exists():
                return []
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
        messages_payload = payload.get("messages", [])
        if not isinstance(messages_payload, list):
            return []
        return [ChatMessage.from_dict(item) for item in messages_payload if isinstance(item, dict)]

    def append_message(self, session_id: str, message: ChatMessage) -> List[ChatMessage]:
        with self._lock:
            messages = self.load_messages(session_id)
            messages.append(message)
            self._write_messages(session_id, messages)
            return messages

    def recent_messages(self, session_id: str, limit: int) -> List[ChatMessage]:
        messages = self.load_messages(session_id)
        if limit <= 0:
            return messages
        return messages[-limit:]

    def clear_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        with self._lock:
            if path.exists():
                path.unlink()

    def delete_messages(self, session_id: str, message_ids: List[str]) -> List[ChatMessage]:
        target_ids: Set[str] = set(message_ids)
        with self._lock:
            messages = self.load_messages(session_id)
            kept_messages = [message for message in messages if message.message_id not in target_ids]
            if len(kept_messages) != len(messages):
                self._write_messages(session_id, kept_messages)
            return kept_messages

    def list_sessions(self) -> List[str]:
        with self._lock:
            return sorted(path.stem for path in self._session_dir.glob("*.json") if path.is_file())

    def _write_messages(self, session_id: str, messages: List[ChatMessage]) -> None:
        path = self._session_path(session_id)
        payload = {
            "session_id": normalize_session_id(session_id),
            "updated_at": _utc_now_text(),
            "messages": [message.to_dict() for message in messages],
        }
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
