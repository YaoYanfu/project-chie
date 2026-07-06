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
import shutil

MessageRole = Literal["user", "assistant", "system"]

_SESSION_ID_PATTERN = re.compile("[^a-zA-Z0-9_.\\-\u3040-\u30ff\u3400-\u9fff]+")
_MESSAGE_ID_PATTERN = re.compile("[^a-zA-Z0-9_.\\-]+")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_session_id(session_id: str) -> str:
    normalized = _SESSION_ID_PATTERN.sub("_", session_id.strip())
    normalized = normalized.strip("._-")
    return normalized or "default"


def normalize_message_id(message_id: str) -> str:
    normalized = _MESSAGE_ID_PATTERN.sub("_", message_id.strip())
    normalized = normalized.strip("._-")
    return normalized or "message"


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
    voice_text: str = ""
    voice_url: str = ""

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
        voice_text = str(payload.get("voice_text") or "")
        voice_url = str(payload.get("voice_url") or "")
        message_id = str(payload.get("message_id") or _build_legacy_message_id(role, content, created_at, source))
        return cls(
            message_id=message_id,
            role=role,
            content=content,
            created_at=created_at,
            source=source,
            voice_text=voice_text,
            voice_url=voice_url,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConversationStore:
    """基于 JSON 文件的轻量会话存储。"""

    def __init__(self, data_dir: Path):
        self._session_dir = data_dir / "sessions"
        self._voice_dir = data_dir / "voices"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _session_path(self, session_id: str) -> Path:
        safe_session_id = normalize_session_id(session_id)
        return self._session_dir / f"{safe_session_id}.json"

    def _voice_session_dir(self, session_id: str) -> Path:
        safe_session_id = normalize_session_id(session_id)
        return self._voice_dir / safe_session_id

    def _voice_path(self, session_id: str, message_id: str) -> Path:
        safe_message_id = normalize_message_id(message_id)
        return self._voice_session_dir(session_id) / f"{safe_message_id}.wav"

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
            voice_dir = self._voice_session_dir(session_id)
            if voice_dir.exists():
                shutil.rmtree(voice_dir)

    def delete_messages(self, session_id: str, message_ids: List[str]) -> List[ChatMessage]:
        target_ids: Set[str] = set(message_ids)
        with self._lock:
            messages = self.load_messages(session_id)
            kept_messages = [message for message in messages if message.message_id not in target_ids]
            if len(kept_messages) != len(messages):
                self._write_messages(session_id, kept_messages)
                for message_id in target_ids:
                    self.delete_voice(session_id, message_id)
            return kept_messages

    def list_sessions(self) -> List[str]:
        with self._lock:
            return sorted(path.stem for path in self._session_dir.glob("*.json") if path.is_file())

    def list_sessions_with_meta(self) -> List[Dict[str, Any]]:
        """返回会话列表，附带最近一条消息预览和消息数量。"""
        with self._lock:
            result: List[Dict[str, Any]] = []
            session_files = sorted(
                self._session_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for path in session_files:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                messages_payload = payload.get("messages", [])
                if not isinstance(messages_payload, list):
                    continue
                messages = [
                    ChatMessage.from_dict(item) for item in messages_payload if isinstance(item, dict)
                ]
                preview = ""
                last_role = ""
                if messages:
                    last_msg = messages[-1]
                    preview = last_msg.content[:80] + ("..." if len(last_msg.content) > 80 else "")
                    last_role = last_msg.role
                result.append({
                    "session_id": path.stem,
                    "last_message_preview": preview,
                    "last_message_role": last_role,
                    "message_count": len(messages),
                })
            return result

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

    def build_voice_url(self, session_id: str, message_id: str) -> str:
        safe_session_id = normalize_session_id(session_id)
        safe_message_id = normalize_message_id(message_id)
        return f"/api/sessions/{safe_session_id}/voices/{safe_message_id}.wav"

    def save_voice(self, session_id: str, message_id: str, voice_bytes: bytes) -> str:
        with self._lock:
            voice_dir = self._voice_session_dir(session_id)
            voice_dir.mkdir(parents=True, exist_ok=True)
            self._voice_path(session_id, message_id).write_bytes(voice_bytes)
        return self.build_voice_url(session_id, message_id)

    def load_voice(self, session_id: str, message_id: str) -> bytes | None:
        path = self._voice_path(session_id, message_id)
        with self._lock:
            if not path.exists() or not path.is_file():
                return None
            return path.read_bytes()

    def delete_voice(self, session_id: str, message_id: str) -> None:
        path = self._voice_path(session_id, message_id)
        if path.exists():
            path.unlink()

    def update_message_voice(
        self,
        session_id: str,
        message_id: str,
        voice_text: str,
        voice_url: str,
    ) -> List[ChatMessage]:
        with self._lock:
            messages = self.load_messages(session_id)
            for message in messages:
                if message.message_id == message_id:
                    message.voice_text = voice_text
                    message.voice_url = voice_url
                    self._write_messages(session_id, messages)
                    break
            return messages
