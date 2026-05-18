from typing import Optional, TYPE_CHECKING

import hashlib
import random
import re

import httpx

from src.common.data_models.message_component_data_model import (
    AtComponent,
    EmojiComponent,
    ForwardNodeComponent,
    ImageComponent,
    ReplyComponent,
    TextComponent,
    VoiceComponent,
)
from src.common.logger import get_logger

logger = get_logger("tts_utils")

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage


VOICE_REQUEST_KEYWORDS = (
    "发语音",
    "发个语音",
    "发条语音",
    "发一条语音",
    "发段语音",
    "语音回复",
    "用语音",
    "来句语音",
    "来段语音",
    "来个语音",
    "说句话",
    "说一声",
    "说两句",
    "说给我听",
    "念一下",
    "念给我听",
    "读一下",
    "读给我听",
    "听听你的声音",
    "想听你声音",
    "开麦",
    "语音输入",
    "voice",
    "audio",
)

VOICE_REJECT_KEYWORDS = (
    "不要发语音",
    "别发语音",
    "不用语音",
    "不要语音",
    "别语音",
    "文字就行",
    "打字就行",
)

PRIVATE_DIALOGUE_QUOTE_PATTERNS = (
    re.compile(r"“([^”]{1,800})”", re.DOTALL),
    re.compile(r"「([^」]{1,800})」", re.DOTALL),
    re.compile(r"『([^』]{1,800})』", re.DOTALL),
    re.compile(r"‘([^’]{1,800})’", re.DOTALL),
    re.compile(r'"([^"]{1,800})"', re.DOTALL),
)

PRIVATE_STAGE_DIRECTION_PATTERNS = (
    re.compile(r"\*[^*\n]{1,300}\*"),
    re.compile(r"（[^（）]{1,300}）"),
    re.compile(r"\([^()\n]{1,300}\)"),
    re.compile(r"【[^【】]{1,300}】"),
    re.compile(r"\[[^\[\]\n]{1,300}\]"),
)

PRIVATE_SPEAKER_PREFIX_PATTERN = re.compile(r"^\s*(?:千惠|チエ|chie|assistant|助手)\s*[:：]\s*", re.IGNORECASE)
PRIVATE_NON_SPEECH_PREFIXES = ("旁白", "环境", "场景", "动作", "神态")
PRIVATE_UNQUOTED_NARRATION_PREFIXES = ("千惠", "她", "少女", "房间", "窗外", "空气", "灯光", "雨声", "风声")


def _build_gpt_sovits_payload(text: str) -> dict[str, object]:
    """构造 GPT-SoVITS api_v2.py 的 /tts 请求体。"""
    from src.config.config import global_config

    voice_config = global_config.voice
    ref_audio_path = voice_config.tts_ref_audio_path.strip()
    return {
        "text": text,
        "text_lang": voice_config.tts_text_lang.strip(),
        "ref_audio_path": ref_audio_path,
        "prompt_text": voice_config.tts_prompt_text,
        "prompt_lang": voice_config.tts_prompt_lang.strip(),
        "text_split_method": "cut5",
        "batch_size": 1,
        "media_type": "wav",
        "streaming_mode": False,
        "parallel_infer": True,
    }


def prepare_tts_text(text: str) -> str:
    """清理并按配置截断待合成文本。"""
    from src.config.config import global_config

    normalized_text = " ".join(text.split())
    max_length = global_config.voice.tts_max_text_length
    if len(normalized_text) <= max_length:
        return normalized_text
    return normalized_text[:max_length].rstrip()


def _clean_private_dialogue_text(text: str) -> str:
    """清理私密模式中准备朗读的台词文本。"""
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned_text = re.sub(r"```.*?```", "", cleaned_text, flags=re.DOTALL)
    cleaned_text = re.sub(r"https?://\S+", "", cleaned_text)
    cleaned_text = cleaned_text.replace("\u3000", " ")
    cleaned_text = " ".join(cleaned_text.split())
    return cleaned_text.strip(" \t\r\n\"'“”‘’「」『』")


def _join_private_dialogue_segments(segments: list[str]) -> str:
    """把多个台词片段拼成适合一次语音合成的文本。"""
    cleaned_segments = [_clean_private_dialogue_text(segment) for segment in segments]
    return " ".join(segment for segment in cleaned_segments if segment)


def _line_is_non_speech_description(line: str) -> bool:
    """判断一行是否是明确标注的环境或动作描写。"""
    normalized_line = line.lstrip()
    return any(
        normalized_line.startswith(f"{prefix}:") or normalized_line.startswith(f"{prefix}：")
        for prefix in PRIVATE_NON_SPEECH_PREFIXES
    )


def _line_has_private_stage_direction(line: str) -> bool:
    """判断一行是否包含显式动作或神态标记。"""
    return any(pattern.search(line) for pattern in PRIVATE_STAGE_DIRECTION_PATTERNS)


def _line_looks_like_unquoted_narration(line: str) -> bool:
    """粗略跳过未加引号的第三人称或环境描写。"""
    normalized_line = line.lstrip(" \t　")
    return normalized_line.startswith(PRIVATE_UNQUOTED_NARRATION_PREFIXES)


def _extract_dialogue_after_speaker_colon(line: str) -> str:
    """从 ``千惠：...`` 或短动作提示后的冒号中提取台词。"""
    direct_speech = PRIVATE_SPEAKER_PREFIX_PATTERN.sub("", line)
    if direct_speech != line:
        return direct_speech.strip()

    for separator in ("：", ":"):
        prefix, found_separator, suffix = line.partition(separator)
        if not found_separator:
            continue
        normalized_prefix = prefix.strip()
        if 0 < len(normalized_prefix) <= 40 and not normalized_prefix.endswith(("如下", "包括")):
            return suffix.strip()
    return line.strip()


def _remove_private_stage_directions(text: str) -> str:
    """删除一段文本中用常见标记包裹的动作或环境描写。"""
    stripped_text = text
    for pattern in PRIVATE_STAGE_DIRECTION_PATTERNS:
        previous_text = None
        while previous_text != stripped_text:
            previous_text = stripped_text
            stripped_text = pattern.sub("", stripped_text)
    return stripped_text


def _strip_private_stage_directions(text: str) -> str:
    """去掉私密模式回复中的动作、神态、环境描写标记。"""
    speech_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _line_is_non_speech_description(line):
            continue
        line_has_stage_direction = _line_has_private_stage_direction(line)
        line_without_stage = _remove_private_stage_directions(line).strip()
        speech_line = _extract_dialogue_after_speaker_colon(line_without_stage)
        if not line_has_stage_direction and speech_line == line_without_stage and _line_looks_like_unquoted_narration(
            speech_line
        ):
            continue
        if speech_line:
            speech_lines.append(speech_line)
    return _clean_private_dialogue_text("\n".join(speech_lines))


def extract_private_dialogue_tts_text(reply_text: str) -> str:
    """提取私密模式中应由千惠读出来的台词。

    私密模式保留完整文字回复，只把引号中的台词，或去掉动作/神态描写后的直述内容，
    交给 TTS。这样环境描写仍留在文字里，不会被朗读。
    """
    normalized_text = reply_text.strip()
    if not normalized_text:
        return ""

    quoted_segments: list[tuple[int, str]] = []
    for pattern in PRIVATE_DIALOGUE_QUOTE_PATTERNS:
        for match in pattern.finditer(normalized_text):
            dialogue_text = _clean_private_dialogue_text(match.group(1))
            if dialogue_text:
                quoted_segments.append((match.start(), dialogue_text))

    if quoted_segments:
        deduplicated_segments: list[str] = []
        seen_segments: set[str] = set()
        for _, segment in sorted(quoted_segments, key=lambda item: item[0]):
            if segment in seen_segments:
                continue
            seen_segments.add(segment)
            deduplicated_segments.append(segment)
        return _join_private_dialogue_segments(deduplicated_segments)

    return _strip_private_stage_directions(normalized_text)


async def synthesize_voice(text: str) -> Optional[bytes]:
    """将文本合成为语音字节；失败时返回 ``None``。"""
    from src.config.config import global_config

    voice_config = global_config.voice
    if not voice_config.enable_tts:
        return None
    if voice_config.tts_provider.strip().lower() != "gpt_sovits":
        logger.warning(f"暂不支持的语音合成服务: {voice_config.tts_provider}")
        return None
    if not voice_config.tts_ref_audio_path.strip():
        logger.warning("GPT-SoVITS 参考音频路径为空，无法合成语音")
        return None

    tts_text = prepare_tts_text(text)
    if not tts_text:
        return None

    try:
        async with httpx.AsyncClient(timeout=voice_config.tts_timeout) as client:
            response = await client.post(
                voice_config.gpt_sovits_api_url.strip(),
                json=_build_gpt_sovits_payload(tts_text),
            )
        if response.status_code != 200:
            logger.warning(f"GPT-SoVITS 语音合成失败: HTTP {response.status_code}, {response.text[:300]}")
            return None
        if not response.content:
            logger.warning("GPT-SoVITS 语音合成返回空内容")
            return None
        return response.content
    except Exception as exc:
        logger.warning(f"GPT-SoVITS 语音合成请求失败: {exc}")
        return None


def _extract_tts_text(message: "SessionMessage") -> str:
    """提取适合语音合成的文本内容。"""
    text_parts = [
        component.text.strip()
        for component in message.raw_message.components
        if isinstance(component, TextComponent) and component.text.strip()
    ]
    return " ".join(text_parts).strip()


def _extract_message_text(message: "SessionMessage") -> str:
    """提取消息中的可读文本。"""
    text = (message.processed_plain_text or "").strip()
    if text:
        return text
    text_parts = [
        component.text.strip()
        for component in message.raw_message.components
        if isinstance(component, TextComponent) and component.text.strip()
    ]
    return " ".join(text_parts).strip()


def _extract_recent_user_text(message: "SessionMessage") -> str:
    """获取触发本次回复的最近用户消息文本。"""
    session_id = str(message.session_id or "").strip()
    if not session_id:
        return ""
    try:
        from src.chat.message_receive.chat_manager import chat_manager

        session = chat_manager.get_session_by_session_id(session_id)
        context_message = session.context.message if session and session.context else None
        if context_message is not None:
            return _extract_message_text(context_message)
        last_message = chat_manager.last_messages.get(session_id)
        if last_message is not None:
            return _extract_message_text(last_message)
    except Exception as exc:
        logger.debug(f"获取最近用户消息失败: {exc}")
    return ""


def _contains_voice_request(user_text: str) -> bool:
    """粗略识别用户是否主动要求语音回复。"""
    normalized_text = user_text.lower().replace(" ", "")
    if not normalized_text:
        return False
    if any(keyword in normalized_text for keyword in VOICE_REJECT_KEYWORDS):
        return False
    return any(keyword in normalized_text for keyword in VOICE_REQUEST_KEYWORDS)


async def _llm_should_send_voice(message: "SessionMessage", user_text: str, reply_text: str) -> bool:
    """让模型判断本次回复是否适合发语音。"""
    from src.common.data_models.llm_service_data_models import LLMGenerationOptions
    from src.config.config import global_config
    from src.services.llm_service import LLMServiceClient

    prompt = (
        "你是千惠的发送形式决策器。请判断这次回复是否应该以语音消息发送。\n"
        "只输出 VOICE 或 TEXT，不要输出解释。\n\n"
        "判断规则：\n"
        "1. 只有用户主动要求千惠发语音、开麦、说给他听、读出来、听听声音时，才允许 VOICE。\n"
        "2. 如果用户明确要求不要语音、文字回复、打字就行，输出 TEXT。\n"
        "3. 如果用户确实要求语音，大多数情况输出 VOICE。\n"
        "4. 如果千惠准备回复的内容很长、包含代码/链接/列表、或不适合朗读，输出 TEXT。\n\n"
        f"千惠昵称：{global_config.bot.nickname}\n"
        f"用户最近发言：{user_text}\n"
        f"千惠准备回复：{reply_text}\n"
    )
    try:
        llm_client = LLMServiceClient(
            task_name="utils",
            request_type="tts_decision",
            session_id=str(message.session_id or ""),
        )
        result = await llm_client.generate_response(
            prompt,
            LLMGenerationOptions(temperature=0, max_tokens=8, raise_when_empty=False),
        )
        decision = result.response.strip().upper()
        if "VOICE" in decision:
            return True
        if "TEXT" in decision:
            return False
        logger.debug(f"语音发送模型判断返回未知结果，默认发语音: {result.response!r}")
        return True
    except Exception as exc:
        logger.warning(f"语音发送模型判断失败，默认按用户请求发语音: {exc}")
        return True


def _message_can_be_converted_to_voice(message: "SessionMessage") -> bool:
    """判断当前出站消息是否适合转换为语音。"""
    from src.config.config import global_config

    if not global_config.voice.enable_tts:
        return False

    components = message.raw_message.components
    if any(isinstance(component, VoiceComponent) for component in components):
        return False
    if any(isinstance(component, (ImageComponent, EmojiComponent, ForwardNodeComponent)) for component in components):
        return False
    return bool(_extract_tts_text(message))


async def convert_text_message_to_voice(message: "SessionMessage") -> bool:
    """将文本出站消息转换为语音组件。"""
    from src.config.config import global_config

    if not _message_can_be_converted_to_voice(message):
        return True

    text = _extract_tts_text(message)
    user_text = _extract_recent_user_text(message)
    voice_requested = _contains_voice_request(user_text)
    if global_config.voice.tts_only_when_requested and not voice_requested:
        return True
    if voice_requested and global_config.voice.tts_enable_llm_decision:
        should_send_voice = await _llm_should_send_voice(message, user_text, text)
        if not should_send_voice:
            logger.info("用户提到了语音，但模型判断本次仍使用文字回复")
            return True
    if random.random() > global_config.voice.tts_send_probability:
        return True

    voice_bytes = await synthesize_voice(text)
    if not voice_bytes:
        return global_config.voice.tts_fallback_to_text

    preserved_components = [
        component
        for component in message.raw_message.components
        if isinstance(component, (ReplyComponent, AtComponent))
    ]
    voice_hash = hashlib.sha256(voice_bytes).hexdigest()
    preserved_components.append(VoiceComponent(binary_hash=voice_hash, content=text, binary_data=voice_bytes))
    message.raw_message.components = preserved_components
    logger.info("已将文本回复转换为千惠语音")
    return True
