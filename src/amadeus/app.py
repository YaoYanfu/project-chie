"""Amadeus 本机 FastAPI 应用。"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import urlsplit

import asyncio

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .chat import ChatRelay
from .remote import RemoteMaiBotClient
from .settings import AmadeusSettings
from .storage import AmadeusStore
from .tts import TtsService


class RemoteConfigRequest(BaseModel):
    remote_base_url: str = Field(min_length=1, max_length=2048)
    remote_token: str = Field(pattern="^[0-9a-fA-F]{64}$")
    owner_person_id: str = Field(min_length=1, max_length=255)


class CommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)


class CommandDecisionRequest(BaseModel):
    approved: bool
    reason: str = Field(default="", max_length=500)


class StatusMonitor:
    """轮询云端状态，并只在状态变化时写入事件。"""

    def __init__(self, remote: RemoteMaiBotClient, store: AmadeusStore, interval_seconds: float = 10.0) -> None:
        self._remote = remote
        self._store = store
        self._interval_seconds = interval_seconds
        self._last_online: Optional[bool] = None

    async def run(self) -> None:
        while True:
            await self.check_once()
            await asyncio.sleep(self._interval_seconds)

    async def check_once(self) -> Dict[str, Any]:
        status = await self._remote.get_status()
        online = bool(status.get("online"))
        should_report = self._last_online is not None and online != self._last_online
        should_report_initial_offline = self._last_online is None and bool(status.get("configured")) and not online
        if should_report or should_report_initial_offline:
            self._store.add_event(
                "remote.maibot",
                "service.online" if online else "service.offline",
                "云端千惠已恢复在线" if online else "云端千惠已离线",
                status="info" if online else "warning",
                metadata={"reason": str(status.get("reason") or "")},
            )
        self._last_online = online
        return status


def _validate_remote_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(status_code=422, detail="云端地址必须是有效的 http 或 https URL")
    if parts.query or parts.fragment:
        raise HTTPException(status_code=422, detail="云端地址不能包含查询参数或片段")
    return normalized


def create_app(
    data_dir: Optional[Path] = None,
    remote_client: Optional[RemoteMaiBotClient] = None,
    tts_service: Optional[TtsService] = None,
    start_monitor: bool = True,
) -> FastAPI:
    settings = AmadeusSettings(data_dir)
    store = AmadeusStore(settings.data_dir)
    remote = remote_client or RemoteMaiBotClient(settings)
    tts = tts_service or TtsService(settings, store)
    chat_relay = ChatRelay(settings, store)
    monitor = StatusMonitor(remote, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        monitor_task: Optional[asyncio.Task[None]] = None
        if start_monitor:
            monitor_task = asyncio.create_task(monitor.run())
        try:
            yield
        finally:
            if monitor_task:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)

    app = FastAPI(title="Amadeus Local", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.remote = remote
    app.state.tts = tts
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["app://host", "http://127.0.0.1:7999", "http://localhost:7999"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "healthy", "service": "amadeus-local"}

    @app.get("/api/config/remote")
    async def get_remote_config() -> Dict[str, Any]:
        config = settings.load()
        return {
            "remote_base_url": config["remote_base_url"],
            "remote_token_configured": bool(config["remote_token"]),
            "owner_person_id": config["owner_person_id"],
        }

    @app.put("/api/config/remote")
    async def update_remote_config(request: RemoteConfigRequest) -> Dict[str, Any]:
        remote_base_url = _validate_remote_url(request.remote_base_url)
        owner_person_id = request.owner_person_id.strip()
        if not owner_person_id:
            raise HTTPException(status_code=422, detail="owner_person_id 不能为空")
        settings.update_remote(remote_base_url, request.remote_token, owner_person_id)
        store.add_event("amadeus.config", "remote.updated", "云端 Project Chie 连接配置已更新")
        return {
            "success": True,
            "remote_base_url": remote_base_url,
            "remote_token_configured": True,
            "owner_person_id": owner_person_id,
        }

    @app.get("/api/status")
    async def get_status() -> Dict[str, Any]:
        remote_status, identity = await asyncio.gather(remote.get_status(), remote.get_identity())
        return {
            "remote": remote_status,
            "identity": identity,
            "local": {
                "amadeus": {"online": True},
                "tts": tts.status(),
            },
        }

    @app.get("/api/events")
    async def list_events(limit: int = Query(default=100, ge=1, le=500)) -> Dict[str, Any]:
        events = store.list_events(limit)
        return {"events": events, "total": len(events)}

    @app.delete("/api/events/{event_id}")
    async def delete_event(event_id: str) -> Dict[str, bool]:
        if not store.delete_event(event_id):
            raise HTTPException(status_code=404, detail="事件不存在")
        return {"success": True}

    @app.get("/api/chat/messages")
    async def list_chat_messages(limit: int = Query(default=200, ge=1, le=500)) -> Dict[str, Any]:
        messages = store.list_chat_messages(limit)
        return {"messages": messages, "total": len(messages)}

    @app.delete("/api/chat/messages")
    async def clear_chat_messages() -> Dict[str, Any]:
        return {"success": True, "deleted": store.clear_chat_messages()}

    @app.post("/api/commands")
    async def create_command(request: CommandRequest) -> Dict[str, Any]:
        try:
            command = store.create_command(request.action, request.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.add_event(
            "amadeus.command",
            "command.created",
            f"已接收动作请求: {request.action}",
            status="warning" if command["status"] == "pending_approval" else "info",
            metadata={"command_id": command["id"], "command_status": command["status"]},
        )
        return command

    @app.get("/api/commands")
    async def list_commands(
        limit: int = Query(default=100, ge=1, le=500),
        status: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        commands = store.list_commands(limit=limit, status=status)
        return {"commands": commands, "total": len(commands)}

    @app.post("/api/commands/{command_id}/decision")
    async def decide_command(command_id: str, request: CommandDecisionRequest) -> Dict[str, Any]:
        command = store.decide_command(command_id, request.approved, request.reason)
        if command is None:
            raise HTTPException(status_code=409, detail="命令不存在、无需审批或已经处理")
        store.add_event(
            "amadeus.command",
            "command.approved" if request.approved else "command.rejected",
            f"动作请求已{'批准' if request.approved else '拒绝'}: {command['action']}",
            metadata={"command_id": command_id},
        )
        return command

    @app.post("/api/services/tts/start")
    async def start_tts() -> Dict[str, Any]:
        try:
            return tts.start()
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/services/tts/stop")
    async def stop_tts() -> Dict[str, Any]:
        try:
            return tts.stop()
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.websocket("/api/chat/ws")
    async def chat_websocket(websocket: WebSocket) -> None:
        await chat_relay.handle(websocket)

    return app
