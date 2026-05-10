"""本地控制台 FastAPI 应用。"""

from pathlib import Path
from secrets import compare_digest
from typing import List, Optional

import json

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import LocalChatEngine, LocalModelError
from .settings import LocalConsoleSettings
from .storage import ChatMessage, ConversationStore, normalize_session_id


class MessagePayload(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: str
    source: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(default="default", min_length=1, max_length=120)


class DeleteMessagesRequest(BaseModel):
    message_ids: List[str] = Field(min_length=1, max_length=200)


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: MessagePayload
    messages: List[MessagePayload]
    model_enabled: bool
    model_name: str


class MessagesResponse(BaseModel):
    session_id: str
    messages: List[MessagePayload]


class SessionsResponse(BaseModel):
    sessions: List[str]


class StatusResponse(BaseModel):
    host: str
    port: int
    model_enabled: bool
    model_name: str
    base_url: str
    context_window: int
    disable_thinking: bool
    data_dir: str


def _message_to_payload(message: ChatMessage) -> MessagePayload:
    return MessagePayload(
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        source=message.source,
    )


def _extract_token(
    authorization: Optional[str],
    header_token: Optional[str],
    query_token: Optional[str],
) -> Optional[str]:
    if header_token:
        return header_token
    if query_token:
        return query_token
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def create_app(settings: Optional[LocalConsoleSettings] = None) -> FastAPI:
    """创建本地控制台应用实例。"""

    effective_settings = settings or LocalConsoleSettings.from_env()
    store = ConversationStore(effective_settings.data_dir)
    engine = LocalChatEngine(effective_settings)
    index_path = Path(__file__).resolve().parent / "static" / "index.html"

    app = FastAPI(title="MaiBot 本地控制台")
    app.mount("/assets", StaticFiles(directory=index_path.parent), name="local_console_assets")

    async def require_auth(
        authorization: Optional[str] = Header(default=None),
        x_local_console_token: Optional[str] = Header(default=None),
        token: Optional[str] = Query(default=None),
    ) -> None:
        provided_token = _extract_token(authorization, x_local_console_token, token)
        if not provided_token or not compare_digest(provided_token, effective_settings.access_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="本地控制台访问令牌无效",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(token: Optional[str] = Query(default=None)) -> HTMLResponse:
        html = index_path.read_text(encoding="utf-8")
        html = html.replace("__INITIAL_TOKEN__", json.dumps(token or "", ensure_ascii=False))
        return HTMLResponse(content=html)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/status", response_model=StatusResponse, dependencies=[Depends(require_auth)])
    async def get_status() -> StatusResponse:
        return StatusResponse(
            host=effective_settings.host,
            port=effective_settings.port,
            model_enabled=effective_settings.model_enabled,
            model_name=effective_settings.model,
            base_url=effective_settings.base_url,
            context_window=effective_settings.context_window,
            disable_thinking=effective_settings.disable_thinking,
            data_dir=str(effective_settings.data_dir),
        )

    @app.get("/api/sessions", response_model=SessionsResponse, dependencies=[Depends(require_auth)])
    async def list_sessions() -> SessionsResponse:
        return SessionsResponse(sessions=store.list_sessions())

    @app.get(
        "/api/sessions/{session_id}/messages",
        response_model=MessagesResponse,
        dependencies=[Depends(require_auth)],
    )
    async def get_messages(session_id: str) -> MessagesResponse:
        safe_session_id = normalize_session_id(session_id)
        messages = store.load_messages(safe_session_id)
        return MessagesResponse(
            session_id=safe_session_id,
            messages=[_message_to_payload(message) for message in messages],
        )

    @app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_auth)])
    async def chat(request: ChatRequest) -> ChatResponse:
        safe_session_id = normalize_session_id(request.session_id)
        user_text = request.message.strip()
        if not user_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息不能为空")

        store.append_message(safe_session_id, ChatMessage.create("user", user_text))
        recent_messages = store.recent_messages(safe_session_id, effective_settings.max_history_messages)
        try:
            reply_result = await engine.generate_reply(recent_messages)
        except LocalModelError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        assistant_message = ChatMessage.create("assistant", reply_result.content)
        all_messages = store.append_message(safe_session_id, assistant_message)

        return ChatResponse(
            session_id=safe_session_id,
            assistant_message=_message_to_payload(assistant_message),
            messages=[_message_to_payload(message) for message in all_messages],
            model_enabled=reply_result.model_enabled,
            model_name=reply_result.model_name,
        )

    @app.post(
        "/api/sessions/{session_id}/messages/delete",
        response_model=MessagesResponse,
        dependencies=[Depends(require_auth)],
    )
    async def delete_messages(session_id: str, request: DeleteMessagesRequest) -> MessagesResponse:
        safe_session_id = normalize_session_id(session_id)
        messages = store.delete_messages(safe_session_id, request.message_ids)
        return MessagesResponse(
            session_id=safe_session_id,
            messages=[_message_to_payload(message) for message in messages],
        )

    @app.post(
        "/api/sessions/{session_id}/clear",
        response_model=MessagesResponse,
        dependencies=[Depends(require_auth)],
    )
    async def clear_session(session_id: str) -> MessagesResponse:
        safe_session_id = normalize_session_id(session_id)
        store.clear_session(safe_session_id)
        return MessagesResponse(session_id=safe_session_id, messages=[])

    return app
