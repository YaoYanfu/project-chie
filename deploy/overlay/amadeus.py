"""Amadeus 系统 API 路由 —— AI 实体管理面板。"""

from typing import Optional

import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.common.logger import get_logger
from src.config.config import MMC_VERSION
from src.webui.core import COOKIE_NAME, COOKIE_MAX_AGE, get_token_manager, set_auth_cookie
from src.webui.dependencies import require_auth

router = APIRouter(prefix="/amadeus", tags=["Amadeus"])
logger = get_logger("amadeus")

_START_TIME = time.time()


def _get_process():
    """延迟导入 psutil，避免模块加载失败。"""
    import psutil
    return psutil.Process()


def _get_psutil():
    """延迟导入 psutil。"""
    import psutil
    return psutil
_PROJECT_ROOT = os.environ.get("MAIBOT_PROJECT_ROOT", "")


# ── 数据模型 ──────────────────────────────────────────────────────────────

class AmadeusLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AmadeusSetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class AmadeusAuthResponse(BaseModel):
    success: bool
    message: str
    is_first_setup: bool = False


class AmadeusStatusResponse(BaseModel):
    # 核心状态
    bot_running: bool
    bot_start_time: str
    model_name: str
    model_context_window: int
    model_disable_thinking: bool
    memory_total_entries: int
    tts_enabled: bool
    tts_running: bool
    # 扩展参数
    private_console_running: bool
    uptime_seconds: float
    today_message_count: int
    # 系统资源
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    # 元信息
    version: str
    bot_nickname: str


class AmadeusBotControlResponse(BaseModel):
    success: bool
    message: str
    url: str = ""


class AmadeusServiceStatusResponse(BaseModel):
    running: bool
    port: int
    url: str


class AmadeusServiceLaunchResponse(BaseModel):
    success: bool
    message: str
    script: str
    args: list[str] = Field(default_factory=list)


# ── 认证辅助 ─────────────────────────────────────────────────────────────

def _get_amadeus_config_path() -> str:
    """获取 Amadeus 凭证存储路径（与 webui.json 同目录）。"""
    token_manager = get_token_manager()
    return str(token_manager.config_path)


def _load_amadeus_credentials() -> dict:
    """从 webui.json 中读取 Amadeus 凭证。"""
    try:
        with open(_get_amadeus_config_path(), "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("amadeus_credentials", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _save_amadeus_credentials(username: str, password_hash: str, salt: str) -> None:
    """保存 Amadeus 凭证到 webui.json。"""
    config_path = _get_amadeus_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError):
        config = {}

    config["amadeus_credentials"] = {
        "username": username,
        "password_hash": password_hash,
        "salt": salt,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _hash_password(password: str, salt: str) -> str:
    """用 PBKDF2-SHA256 对密码做加盐哈希。"""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()


def _is_amadeus_configured() -> bool:
    """检查是否已设置 Amadeus 用户名密码。"""
    creds = _load_amadeus_credentials()
    return bool(creds.get("username") and creds.get("password_hash"))

# ── 状态查询辅助 ─────────────────────────────────────────────────────────

def _get_today_message_count() -> int:
    """查询今日消息数。"""
    try:
        from src.common.database.database import get_db_session
        from src.common.database.database_model import MaiMessages
        from datetime import datetime, timezone
        from sqlmodel import col, func, select

        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with get_db_session() as session:
            stmt = select(func.count()).select_from(MaiMessages).where(
                col(MaiMessages.created_at) >= today_utc
            )
            return int(session.exec(stmt).one())
    except Exception:
        return 0


def _get_memory_entry_count() -> int:
    """查询 A_Memorix 长期记忆条目数。"""
    try:
        from src.A_memorix.core.memory_faiss import get_total_memory_count
        return get_total_memory_count()
    except Exception:
        try:
            from src.common.database.database import get_db_session
            from sqlmodel import func, select
            from src.common.database.database_model import MemoryEntries
            with get_db_session() as session:
                stmt = select(func.count()).select_from(MemoryEntries)
                return int(session.exec(stmt).one())
        except Exception:
            return 0


def _check_port(host: str, port: int) -> bool:
    """检查指定端口是否有服务在监听（使用标准库 socket）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def _kill_process_on_port(port: int) -> bool:
    """杀掉占用指定端口的进程。成功返回 True。"""
    try:
        import psutil
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr.port == port and conn.pid:
                proc = psutil.Process(conn.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                return True
    except Exception:
        pass
    return False


def _resolve_project_root() -> str:
    root = os.environ.get("MAIBOT_PROJECT_ROOT", "")
    if not root:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return root


# ── 公开端点（不需要 Amadeus 认证）───────────────────────────────────────

@router.get("/auth/configured")
async def amadeus_auth_configured():
    """检查 Amadeus 是否已完成首次配置（无需认证即可调用）。"""
    return {"configured": _is_amadeus_configured()}


@router.post("/auth/login")
async def amadeus_login(request_body: AmadeusLoginRequest, response: Response):
    """Amadeus 用户名密码登录：验证通过后设置 WebUI 会话 Cookie。"""
    creds = _load_amadeus_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail="Amadeus 尚未配置，请先设置用户名密码")

    salt = creds.get("salt", "")
    expected_hash = creds.get("password_hash", "")
    if not secrets.compare_digest(creds.get("username", ""), request_body.username):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not secrets.compare_digest(_hash_password(request_body.password, salt), expected_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token_manager = get_token_manager()
    session_token = token_manager.get_token()
    set_auth_cookie(response, session_token)
    return {"success": True, "message": "登录成功"}


@router.post("/auth/setup")
async def amadeus_setup(request_body: AmadeusSetupRequest, response: Response):
    """首次设置 Amadeus 用户名密码（仅在未配置时可用）。"""
    if _is_amadeus_configured():
        raise HTTPException(status_code=409, detail="Amadeus 已配置，如需重置请联系管理员")

    salt = secrets.token_hex(16)
    password_hash = _hash_password(request_body.password, salt)
    _save_amadeus_credentials(request_body.username, password_hash, salt)

    token_manager = get_token_manager()
    session_token = token_manager.get_token()
    set_auth_cookie(response, session_token)
    logger.info(f"Amadeus 首次配置完成，用户: {request_body.username}")
    return {"success": True, "message": "配置完成，已登录"}


# ── 状态端点 ──────────────────────────────────────────────────────────────

@router.get("/status", response_model=AmadeusStatusResponse, dependencies=[Depends(require_auth)])
async def get_amadeus_status():
    """获取 Amadeus 面板所需的所有状态参数。"""
    from src.config.config import global_config, model_config

    bot_config = global_config.bot
    voice_config = global_config.voice

    # 模型名：优先环境变量，其次 model_config.toml 第一个模型，最后兜底
    model_name = os.environ.get("MAIBOT_LOCAL_MODEL_NAME", "").strip()
    if not model_name and model_config.models:
        model_name = model_config.models[0].name or "未知"
    if not model_name:
        model_name = "未知"

    # 上下文窗口
    context_window = int(os.environ.get("MAIBOT_LOCAL_MODEL_NUM_CTX", "0") or 0)
    if context_window <= 0 and model_config.models:
        ctx = getattr(model_config.models[0], "num_ctx", 0) or 0
        if ctx:
            context_window = ctx

    tts_running = _check_port("127.0.0.1", 9880)
    console_running = _check_port("127.0.0.1", 7860)

    # 系统资源（psutil 可选）
    cpu_val = 0.0
    mem_pct = 0.0
    mem_used = 0.0
    mem_total = 0.0
    try:
        import psutil
        proc = psutil.Process()
        cpu_val = proc.cpu_percent(interval=0.1)
        mem_pct = proc.memory_percent()
        mem_used = proc.memory_info().rss / (1024 * 1024)
        mem_total = psutil.virtual_memory().total / (1024 * 1024)
    except Exception:
        pass

    return AmadeusStatusResponse(
        # 核心
        bot_running=True,
        bot_start_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_START_TIME)),
        model_name=model_name,
        model_context_window=context_window,
        model_disable_thinking=os.environ.get("MAIBOT_LOCAL_MODEL_DISABLE_THINKING", "1") == "1",
        memory_total_entries=_get_memory_entry_count(),
        tts_enabled=voice_config.enable_tts,
        tts_running=tts_running,
        # 扩展
        private_console_running=console_running,
        uptime_seconds=time.time() - _START_TIME,
        today_message_count=_get_today_message_count(),
        # 系统资源
        cpu_percent=cpu_val,
        memory_percent=mem_pct,
        memory_used_mb=mem_used,
        memory_total_mb=mem_total,
        # 元信息
        version=MMC_VERSION,
        bot_nickname=bot_config.nickname,
    )

# ── Bot 控制端点 ──────────────────────────────────────────────────────────

@router.post("/bot/stop", response_model=AmadeusBotControlResponse, dependencies=[Depends(require_auth)])
async def stop_bot():
    """发送停止信号，触发 Project Chie 优雅关闭。"""
    try:
        from src.core.event_bus import event_bus
        from src.core.types import EventType
        from src.common.runtime_loop import run_on_main_loop
        from src.manager.async_task_manager import async_task_manager

        async def _shutdown():
            logger.info("Amadeus 面板请求关闭 Bot")
            try:
                await event_bus.emit(event_type=EventType.ON_STOP)
            except Exception:
                pass
            try:
                from src.plugin_runtime.integration import get_plugin_runtime_manager
                await get_plugin_runtime_manager().stop()
            except Exception:
                pass
            try:
                await async_task_manager.stop_and_wait_all_tasks()
            except Exception:
                pass

        asyncio.create_task(_shutdown())
        return AmadeusBotControlResponse(success=True, message="Bot 正在关闭")

    except Exception as e:
        logger.error(f"停止 Bot 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── 私密控制台端点 ────────────────────────────────────────────────────────

_CONSOLE_TOKEN_KEY = "private_console_token"


def _get_console_token() -> str:
    """从 webui.json 读取或生成私密控制台令牌。"""
    try:
        with open(_get_amadeus_config_path(), "r", encoding="utf-8") as f:
            config = json.load(f)
        token = config.get(_CONSOLE_TOKEN_KEY, "")
        if token:
            return token
    except (OSError, json.JSONDecodeError):
        config = {}
    token = secrets.token_hex(16)
    config[_CONSOLE_TOKEN_KEY] = token
    try:
        with open(_get_amadeus_config_path(), "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return token


@router.get("/private-console/status", response_model=AmadeusServiceStatusResponse, dependencies=[Depends(require_auth)])
async def get_private_console_status():
    """查询私密控制台运行状态（端口 7860）。"""
    running = _check_port("127.0.0.1", 7860)
    token = _get_console_token()
    return AmadeusServiceStatusResponse(
        running=running,
        port=7860,
        url=f"http://127.0.0.1:7860/?token={token}" if running else "",
    )


@router.post("/private-console/launch", response_model=AmadeusBotControlResponse, dependencies=[Depends(require_auth)])
async def launch_private_console():
    """后台启动私密控制台。"""
    if _check_port("127.0.0.1", 7860):
        token = _get_console_token()
        return AmadeusBotControlResponse(
            success=True, message="私密控制台已在运行",
            url=f"http://127.0.0.1:7860/?token={token}",
        )
    try:
        root = _resolve_project_root()
        script = os.path.join(root, "scripts", "start_private_console.ps1")
        if not os.path.isfile(script):
            raise HTTPException(status_code=404, detail=f"脚本未找到: {script}")
        token = _get_console_token()
        subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script, "-NoBrowser", "-Token", token],
            cwd=root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        logger.info("Amadeus 面板触发私密控制台启动")
        return AmadeusBotControlResponse(
            success=True, message="私密控制台正在启动，请稍候…",
            url=f"http://127.0.0.1:7860/?token={token}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动私密控制台失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/private-console/stop", response_model=AmadeusBotControlResponse, dependencies=[Depends(require_auth)])
async def stop_private_console():
    """关闭私密控制台（杀掉占用 7860 端口的进程）。"""
    if not _check_port("127.0.0.1", 7860):
        return AmadeusBotControlResponse(success=True, message="私密控制台已停止")
    try:
        if _kill_process_on_port(7860):
            logger.info("Amadeus 面板请求关闭私密控制台")
            return AmadeusBotControlResponse(success=True, message="私密控制台已关闭")
        else:
            return AmadeusBotControlResponse(success=False, message="未能找到私密控制台进程")
    except Exception as e:
        logger.error(f"关闭私密控制台失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── 语音/TTS 端点 ─────────────────────────────────────────────────────────

@router.get("/tts/status", response_model=AmadeusServiceStatusResponse, dependencies=[Depends(require_auth)])
async def get_tts_status():
    """查询 GPT-SoVITS 服务运行状态（端口 9880）。"""
    running = _check_port("127.0.0.1", 9880)
    return AmadeusServiceStatusResponse(
        running=running,
        port=9880,
        url="http://127.0.0.1:9880/tts" if running else "",
    )


@router.post("/tts/launch", response_model=AmadeusBotControlResponse, dependencies=[Depends(require_auth)])
async def launch_tts():
    """后台启动 GPT-SoVITS 语音服务。"""
    if _check_port("127.0.0.1", 9880):
        return AmadeusBotControlResponse(success=True, message="语音服务已在运行")
    try:
        root = _resolve_project_root()
        script = os.path.join(root, "scripts", "start_tts_server.ps1")
        if not os.path.isfile(script):
            raise HTTPException(status_code=404, detail=f"脚本未找到: {script}")
        subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script, "-Background"],
            cwd=root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        logger.info("Amadeus 面板触发 TTS 服务启动")
        return AmadeusBotControlResponse(success=True, message="语音服务正在启动，请稍候…")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动 TTS 服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/tts/stop", response_model=AmadeusBotControlResponse, dependencies=[Depends(require_auth)])
async def stop_tts():
    """关闭语音服务（杀掉占用 9880 端口的进程）。"""
    if not _check_port("127.0.0.1", 9880):
        return AmadeusBotControlResponse(success=True, message="语音服务已停止")
    try:
        if _kill_process_on_port(9880):
            logger.info("Amadeus 面板请求关闭语音服务")
            return AmadeusBotControlResponse(success=True, message="语音服务已关闭")
        else:
            return AmadeusBotControlResponse(success=False, message="未能找到语音服务进程")
    except Exception as e:
        logger.error(f"关闭语音服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

