"""Amadeus 本机到云端 Project Chie 的受限聊天代理。"""

from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

import asyncio
import json

import aiohttp
from fastapi import WebSocket, WebSocketDisconnect

from .settings import AmadeusSettings
from .storage import AmadeusStore

_ALLOWED_CHAT_METHODS = {"session.open", "session.close", "message.send", "session.update_nickname"}


def build_remote_websocket_url(remote_base_url: str) -> str:
    parts = urlsplit(remote_base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    base_path = parts.path.rstrip("/")
    return urlunsplit((scheme, parts.netloc, f"{base_path}/api/webui/ws", "", ""))


def prepare_client_message(message: Dict[str, Any], owner_person_id: str) -> Dict[str, Any]:
    """限制代理能力，并强制使用配置好的主人身份映射。"""
    operation = str(message.get("op") or "")
    if operation == "ping":
        return message

    if operation in {"subscribe", "unsubscribe"}:
        if message.get("domain") == "maisaka_monitor" and message.get("topic") == "main":
            return message
        raise ValueError("Amadeus 代理只允许聊天或订阅千惠心理活动")

    if operation != "call" or message.get("domain") != "chat":
        raise ValueError("Amadeus 代理只允许聊天调用")

    method = str(message.get("method") or "")
    if method not in _ALLOWED_CHAT_METHODS:
        raise ValueError(f"Amadeus 代理不允许聊天方法: {method}")

    if method == "session.open":
        data = message.get("data")
        if not isinstance(data, dict):
            data = {}
        message["data"] = {
            **data,
            "platform": "amadeus",
            "person_id": owner_person_id,
            "group_id": "amadeus_desktop",
            "group_name": "Amadeus 私聊",
        }
    return message


class ChatRelay:
    """在本机与云端之间转发受限的统一 WebSocket 聊天协议。"""

    def __init__(self, settings: AmadeusSettings, store: AmadeusStore) -> None:
        self._settings = settings
        self._store = store

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        config = self._settings.load()
        if not config["remote_base_url"] or not config["remote_token"] or not config["owner_person_id"]:
            await websocket.send_json({"type": "error", "message": "云端连接或主人身份尚未配置"})
            await websocket.close(code=4002)
            return

        remote_url = build_remote_websocket_url(config["remote_base_url"])
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    remote_url,
                    headers={"X-Amadeus-Token": config["remote_token"]},
                    heartbeat=20,
                ) as remote:
                    local_task = asyncio.create_task(self._forward_local(websocket, remote, config["owner_person_id"]))
                    remote_task = asyncio.create_task(self._forward_remote(remote, websocket))
                    done, pending = await asyncio.wait(
                        {local_task, remote_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*done, *pending, return_exceptions=True)
        except (aiohttp.ClientError, OSError) as exc:
            self._store.add_event("remote.maibot", "chat.connection_failed", str(exc), status="error")
            try:
                await websocket.send_json({"type": "error", "message": "无法连接云端千惠"})
                await websocket.close(code=1011)
            except RuntimeError:
                pass

    async def _forward_local(
        self,
        websocket: WebSocket,
        remote: aiohttp.ClientWebSocketResponse,
        owner_person_id: str,
    ) -> None:
        try:
            while True:
                raw_message = await websocket.receive_text()
                try:
                    message = json.loads(raw_message)
                    if not isinstance(message, dict):
                        raise ValueError("消息必须是 JSON 对象")
                    prepared = prepare_client_message(message, owner_person_id)
                except (json.JSONDecodeError, ValueError) as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue

                if prepared.get("method") == "message.send":
                    data = prepared.get("data", {})
                    content = str(data.get("content") or "") if isinstance(data, dict) else ""
                    self._store.add_event(
                        "amadeus.chat",
                        "chat.user_message",
                        content[:160],
                        metadata={"session": str(prepared.get("session") or "")},
                    )
                await remote.send_json(prepared)
        except WebSocketDisconnect:
            await remote.close()

    async def _forward_remote(
        self,
        remote: aiohttp.ClientWebSocketResponse,
        websocket: WebSocket,
    ) -> None:
        async for remote_message in remote:
            if remote_message.type != aiohttp.WSMsgType.TEXT:
                continue
            raw_data = str(remote_message.data)
            try:
                payload = json.loads(raw_data)
                self._record_remote_event(payload)
            except json.JSONDecodeError:
                pass
            await websocket.send_text(raw_data)

    def _record_remote_event(self, payload: Dict[str, Any]) -> None:
        if payload.get("op") != "event" or payload.get("domain") != "chat":
            return
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        event_type = str(data.get("type") or payload.get("event") or "")

        if event_type == "history":
            messages = data.get("messages")
            if not isinstance(messages, list):
                return
            for message in messages:
                if not isinstance(message, dict):
                    continue
                self._store_chat_message(
                    message,
                    role="assistant" if message.get("is_bot") or message.get("type") == "bot" else "user",
                )
            return

        if event_type == "user_message":
            self._store_chat_message(data, role="user")
            return

        if event_type not in {"bot_message", "assistant_message"}:
            return

        self._store_chat_message(data, role="assistant")
        content = str(data.get("content") or "").strip()
        if not content:
            return
        self._store.add_event(
            "remote.maibot",
            "chat.assistant_message",
            content[:160],
            metadata={"session": str(payload.get("session") or "")},
        )

    def _store_chat_message(self, message: Dict[str, Any], role: str) -> None:
        content = str(message.get("content") or "").strip()
        if not content:
            return

        raw_timestamp = message.get("timestamp")
        timestamp = float(raw_timestamp) if isinstance(raw_timestamp, (int, float)) else None
        message_id = str(message.get("id") or message.get("message_id") or "").strip() or None
        self._store.add_chat_message(
            role=role,
            content=content,
            message_id=message_id,
            timestamp=timestamp,
        )
