"""Amadeus 事件、命令和审批记录存储。"""

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

import json
import sqlite3


FREE_ACTIONS = {"message.send", "voice.play"}
APPROVAL_ACTIONS = {"application.open", "command.run", "file.modify", "hardware.control"}
SUPPORTED_ACTIONS = FREE_ACTIONS | APPROVAL_ACTIONS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AmadeusStore:
    """使用本机 SQLite 保存可删除的事件及审批审计记录。"""

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = data_dir / "amadeus.db"
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);

                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decided_at TEXT,
                    decision_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_commands_created_at ON commands(created_at DESC);
                """
            )

    def add_event(
        self,
        source: str,
        event_type: str,
        summary: str,
        status: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "id": uuid4().hex,
            "created_at": _utc_now(),
            "source": source,
            "event_type": event_type,
            "summary": summary,
            "status": status,
            "metadata": metadata or {},
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["id"],
                    event["created_at"],
                    event["source"],
                    event["event_type"],
                    event["summary"],
                    event["status"],
                    json.dumps(event["metadata"], ensure_ascii=False),
                ),
            )
        return event

    def list_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def delete_event(self, event_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
            return cursor.rowcount > 0

    def create_command(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(f"未定义权限策略的动作: {action}")

        status = "accepted" if action in FREE_ACTIONS else "pending_approval"
        command = {
            "id": uuid4().hex,
            "created_at": _utc_now(),
            "action": action,
            "status": status,
            "payload": payload,
            "decided_at": None,
            "decision_reason": "",
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO commands VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    command["id"],
                    command["created_at"],
                    action,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    None,
                    "",
                ),
            )
        return command

    def list_commands(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM commands"
        parameters: List[Any] = []
        if status:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)

        with self._lock, self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._command_from_row(row) for row in rows]

    def decide_command(self, command_id: str, approved: bool, reason: str = "") -> Optional[Dict[str, Any]]:
        decided_at = _utc_now()
        next_status = "approved" if approved else "rejected"
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE commands
                SET status = ?, decided_at = ?, decision_reason = ?
                WHERE id = ? AND status = 'pending_approval'
                """,
                (next_status, decided_at, reason, command_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        return self._command_from_row(row) if row else None

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "source": row["source"],
            "event_type": row["event_type"],
            "summary": row["summary"],
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"]),
        }

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "action": row["action"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "decided_at": row["decided_at"],
            "decision_reason": row["decision_reason"],
        }
