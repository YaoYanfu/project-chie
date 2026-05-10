"""本地控制台回复引擎。"""

from dataclasses import dataclass
from typing import Dict, List, Protocol
from urllib.parse import urljoin

import httpx

from .settings import LocalConsoleSettings
from .storage import ChatMessage


@dataclass(slots=True)
class LocalReplyResult:
    """本地控制台生成结果。"""

    content: str
    model_name: str
    model_enabled: bool


class LocalModelAdapter(Protocol):
    """本地模型适配器接口。"""

    async def generate(self, messages: List[ChatMessage]) -> LocalReplyResult:
        """根据消息历史生成回复。"""


class LocalModelError(Exception):
    """本地模型调用失败。"""


class OllamaLocalModelAdapter:
    """通过 Ollama 原生接口调用本地模型。"""

    def __init__(self, settings: LocalConsoleSettings):
        self._settings = settings
        self._base_url = self._normalize_base_url(settings.base_url)

    async def generate(self, messages: List[ChatMessage]) -> LocalReplyResult:
        payload = self._build_payload(messages)
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
                response = await client.post(urljoin(self._base_url, "/api/chat"), json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LocalModelError(
                f"无法连接本地模型服务：{self._settings.base_url}。"
                "请确认 Ollama 已启动，并且 OLLAMA_MODELS 指向 D:\\JZDSLx\\llm_models。"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LocalModelError(f"本地模型响应超时：{self._settings.model}") from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            if "requires more system memory" in detail:
                detail = (
                    f"{detail}。当前已设置 num_ctx={self._settings.context_window}，"
                    "如果仍然失败，请继续降低 --num-ctx 或换更小/更低量化的模型。"
                )
            raise LocalModelError(f"本地模型调用失败：{detail}") from exc
        except httpx.RequestError as exc:
            raise LocalModelError(f"本地模型请求失败：{exc}") from exc

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise LocalModelError("本地模型返回了非 JSON 响应") from exc

        message = response_payload.get("message") if isinstance(response_payload, dict) else None
        if not isinstance(message, dict):
            raise LocalModelError("本地模型返回格式异常")

        content = message.get("content")
        if isinstance(content, str):
            content = content.strip()
        if not isinstance(content, str) or not content:
            raise LocalModelError(self._build_empty_reply_error(response_payload, message))

        return LocalReplyResult(
            content=content,
            model_name=self._settings.model,
            model_enabled=True,
        )

    def _build_payload(self, messages: List[ChatMessage]) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "model": self._settings.model,
            "messages": self._build_messages(messages),
            "stream": False,
            "options": self._build_options(),
        }
        if self._settings.disable_thinking:
            payload["think"] = False
        return payload

    def _build_messages(self, messages: List[ChatMessage]) -> List[Dict[str, str]]:
        ollama_messages = [{"role": "system", "content": self._build_system_prompt()}]
        for message in messages:
            if message.role not in {"user", "assistant", "system"}:
                continue
            ollama_messages.append({"role": message.role, "content": message.content})
        return ollama_messages

    def _build_system_prompt(self) -> str:
        if not self._settings.disable_thinking:
            return self._settings.system_prompt
        return (
            f"{self._settings.system_prompt}\n"
            "/no_think\n"
            "请直接输出用户可见的最终回复正文。不要只输出思考过程，不要输出空白，不要使用 <think> 标签。"
        )

    def _build_options(self) -> Dict[str, int | float]:
        options: Dict[str, int | float] = {
            "temperature": self._settings.temperature,
            "num_predict": self._settings.max_tokens,
        }
        if self._settings.context_window > 0:
            options["num_ctx"] = self._settings.context_window
        return options

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        return f"{normalized}/"

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
        return f"HTTP {response.status_code}"

    @staticmethod
    def _build_empty_reply_error(response_payload: object, message: Dict[str, object]) -> str:
        payload = response_payload if isinstance(response_payload, dict) else {}
        message_keys = ", ".join(sorted(str(key) for key in message.keys())) or "无"
        done_reason = payload.get("done_reason") or payload.get("done") or "未知"
        thinking = message.get("thinking")
        thinking_length = len(thinking) if isinstance(thinking, str) else 0
        return (
            "本地模型返回了空回复。"
            f"Ollama 响应字段: message_keys={message_keys}, done_reason={done_reason}, "
            f"thinking_len={thinking_length}。"
            "这通常是 Qwen thinking 模式或模型模板兼容导致的。当前请求已发送 think=false 和 /no_think；"
            "如果仍出现，请重启 Ollama 后重试，或把 --num-ctx 降到 1024。"
        )


class PlaceholderLocalModelAdapter:
    """模型尚未下载时使用的占位适配器。"""

    def __init__(self, settings: LocalConsoleSettings):
        self._settings = settings

    async def generate(self, messages: List[ChatMessage]) -> LocalReplyResult:
        last_user_message = self._find_last_user_message(messages)
        preview = f"我已记录你的消息：{last_user_message}" if last_user_message else "我已记录这条消息。"
        if self._settings.model_enabled:
            content = (
                f"{preview}\n\n"
                "本地模型接口已经预留，但当前版本还没有真正发起模型请求。"
                "等模型下载完成后，再把适配器接到本地 OpenAI 兼容接口即可。"
            )
        else:
            content = (
                f"{preview}\n\n"
                "当前处于占位模式：本地模型还未启用，不会调用 DeepSeek 或任何在线模型。"
                "等模型准备好后，再把适配器接到本地 OpenAI 兼容接口即可切换。"
            )
        return LocalReplyResult(
            content=content,
            model_name=self._settings.model,
            model_enabled=self._settings.model_enabled,
        )

    @staticmethod
    def _find_last_user_message(messages: List[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content[:120]
        return ""


class LocalChatEngine:
    """本地控制台聊天引擎。"""

    def __init__(self, settings: LocalConsoleSettings, adapter: LocalModelAdapter | None = None):
        self._settings = settings
        if adapter is not None:
            self._adapter = adapter
        elif settings.model_enabled:
            self._adapter = OllamaLocalModelAdapter(settings)
        else:
            self._adapter = PlaceholderLocalModelAdapter(settings)

    async def generate_reply(self, messages: List[ChatMessage]) -> LocalReplyResult:
        return await self._adapter.generate(messages)
