"""供本机 Amadeus 使用的最小云端桥接 API。"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import col, select

from src.common.database.database import get_db_session
from src.common.database.database_model import PersonInfo
from src.config.config import MMC_VERSION, global_config
from src.webui.dependencies import require_auth
from src.webui.services.amadeus_bridge import get_amadeus_bridge_token_manager

router = APIRouter(prefix="/amadeus/bridge", tags=["AmadeusBridge"])
_STARTED_AT = datetime.now(timezone.utc)
_START_MONOTONIC = time.monotonic()


def require_amadeus_bridge_token(
    x_amadeus_token: Optional[str] = Header(default=None, alias="X-Amadeus-Token"),
) -> str:
    token = x_amadeus_token or ""
    if not get_amadeus_bridge_token_manager().verify(token):
        raise HTTPException(status_code=401, detail="Amadeus bridge token 无效")
    return token


@router.get("/token", dependencies=[Depends(require_auth)])
async def get_bridge_token() -> Dict[str, str]:
    """由 WebUI 管理员读取独立桥接 token，供本机 Amadeus 配置。"""
    return {"token": get_amadeus_bridge_token_manager().get_token()}


@router.post("/token/rotate", dependencies=[Depends(require_auth)])
async def rotate_bridge_token() -> Dict[str, str]:
    """轮换独立桥接 token；旧 token 立即失效。"""
    return {"token": get_amadeus_bridge_token_manager().rotate_token()}


@router.get("/status", dependencies=[Depends(require_amadeus_bridge_token)])
async def get_bridge_status() -> Dict[str, Any]:
    """只要本端点可响应，就表示 MaiBot Worker 与 WebUI 均在线。"""
    return {
        "online": True,
        "service": "maibot",
        "version": MMC_VERSION,
        "bot_nickname": global_config.bot.nickname,
        "started_at": _STARTED_AT.isoformat(),
        "uptime_seconds": time.monotonic() - _START_MONOTONIC,
    }


@router.get("/identity/{person_id}", dependencies=[Depends(require_amadeus_bridge_token)])
async def get_identity_mapping(person_id: str) -> Dict[str, Any]:
    """验证 Amadeus 主人映射；不创建人物，也不计算会话 ID。"""
    with get_db_session() as session:
        statement = select(PersonInfo).where(col(PersonInfo.person_id) == person_id).limit(1)
        person = session.exec(statement).first()
    if person is None:
        return {"online": True, "mapped": False, "person_id": person_id}
    return {
        "online": True,
        "mapped": True,
        "person_id": person.person_id,
        "display_name": person.person_name or person.user_nickname or person.user_id,
        "source_platform": person.platform,
    }
