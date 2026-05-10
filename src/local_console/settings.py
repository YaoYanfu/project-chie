"""本地控制台运行配置。"""

from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

import os

from src.common.logger import get_logger

logger = get_logger("local_console.settings")

DEFAULT_LOCAL_MODEL_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL_NAME = "jaahas/qwen3.5-uncensored:35b"
DEFAULT_LOCAL_MODEL_NUM_CTX = 2048


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning(f"环境变量 {name}={raw_value!r} 不是有效整数，使用默认值 {default}")
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning(f"环境变量 {name}={raw_value!r} 不是有效数字，使用默认值 {default}")
        return default


def _build_default_system_prompt() -> str:
    try:
        from src.config.config import global_config

        bot_config = global_config.bot
        personality_config = global_config.personality
        alias_text = f"，也有人叫你{','.join(bot_config.alias_names)}" if bot_config.alias_names else ""
        personality = personality_config.personality.strip()
        reply_style = personality_config.reply_style.strip()
        prompt_parts = [
            f"你的名字是{bot_config.nickname}{alias_text}。",
            personality,
            reply_style,
            "你正在通过本地控制台和用户私聊，请自然、直接、连贯地回复。",
        ]
        return "\n".join(part for part in prompt_parts if part)
    except Exception as exc:
        logger.warning(f"读取主配置构造本地控制台提示词失败，使用默认提示词: {exc}")
        return "你的名字是千惠。你正在通过本地控制台和用户私聊，请自然、直接、连贯地回复。"


def _default_data_dir() -> Path:
    return Path(os.getenv("MAIBOT_LOCAL_CONSOLE_DATA_DIR", "data/local_console")).resolve()


@dataclass(slots=True)
class LocalConsoleSettings:
    """本地控制台配置。"""

    host: str = "127.0.0.1"
    port: int = 7860
    base_url: str = DEFAULT_LOCAL_MODEL_BASE_URL
    model: str = DEFAULT_LOCAL_MODEL_NAME
    api_key: str = "local"
    access_token: str = field(default_factory=lambda: token_urlsafe(24))
    data_dir: Path = field(default_factory=_default_data_dir)
    system_prompt: str = field(default_factory=_build_default_system_prompt)
    max_history_messages: int = 16
    request_timeout: float = 180.0
    temperature: float = 0.7
    max_tokens: int = 768
    context_window: int = DEFAULT_LOCAL_MODEL_NUM_CTX
    disable_thinking: bool = True
    model_enabled: bool = True
    allow_remote_access: bool = False

    @classmethod
    def from_env(
        cls,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        access_token: Optional[str] = None,
        context_window: Optional[int] = None,
        disable_thinking: Optional[bool] = None,
        model_enabled: Optional[bool] = None,
    ) -> "LocalConsoleSettings":
        """从环境变量和命令行覆盖项构造配置。"""

        token = access_token or os.getenv("MAIBOT_LOCAL_CONSOLE_TOKEN") or token_urlsafe(24)
        return cls(
            host=host or os.getenv("MAIBOT_LOCAL_CONSOLE_HOST", "127.0.0.1"),
            port=port or _env_int("MAIBOT_LOCAL_CONSOLE_PORT", 7860),
            base_url=base_url or os.getenv("MAIBOT_LOCAL_MODEL_BASE_URL", DEFAULT_LOCAL_MODEL_BASE_URL),
            model=model or os.getenv("MAIBOT_LOCAL_MODEL_NAME", DEFAULT_LOCAL_MODEL_NAME),
            api_key=os.getenv("MAIBOT_LOCAL_MODEL_API_KEY", "local"),
            access_token=token,
            data_dir=_default_data_dir(),
            system_prompt=os.getenv("MAIBOT_LOCAL_CONSOLE_SYSTEM_PROMPT") or _build_default_system_prompt(),
            max_history_messages=_env_int("MAIBOT_LOCAL_CONSOLE_MAX_HISTORY", 16),
            request_timeout=_env_float("MAIBOT_LOCAL_MODEL_TIMEOUT", 180.0),
            temperature=_env_float("MAIBOT_LOCAL_MODEL_TEMPERATURE", 0.7),
            max_tokens=_env_int("MAIBOT_LOCAL_MODEL_MAX_TOKENS", 768),
            context_window=context_window
            if context_window is not None
            else _env_int("MAIBOT_LOCAL_MODEL_NUM_CTX", DEFAULT_LOCAL_MODEL_NUM_CTX),
            disable_thinking=disable_thinking
            if disable_thinking is not None
            else _env_bool("MAIBOT_LOCAL_MODEL_DISABLE_THINKING", True),
            model_enabled=model_enabled
            if model_enabled is not None
            else _env_bool("MAIBOT_LOCAL_MODEL_ENABLED", True),
            allow_remote_access=_env_bool("MAIBOT_LOCAL_CONSOLE_ALLOW_REMOTE", False),
        )

    @property
    def is_loopback_only(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    def validate_network_policy(self) -> None:
        """检查网络暴露策略。"""

        if self.is_loopback_only:
            return
        if self.allow_remote_access:
            return
        raise ValueError(
            "本地控制台默认只允许监听 127.0.0.1。"
            "如果要通过 Tailscale 或局域网访问，请设置 MAIBOT_LOCAL_CONSOLE_ALLOW_REMOTE=1。"
        )
