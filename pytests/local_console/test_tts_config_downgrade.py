"""语音功能配置降级行为测试。

关键契约：provider 不受支持或参考音频未配置属于**配置错误**，应抛出
``TtsConfigurationError`` 让调用方降级为文本发送；而不是返回 ``None``，
否则会与"合成失败"混同，在关闭 ``tts_fallback_to_text`` 时把用户回复整条丢掉。
"""

import pytest

from src.common.utils.utils_tts import (
    TtsConfigurationError,
    convert_text_message_to_voice,
    extract_private_dialogue_tts_text,
    prepare_tts_text,
    synthesize_voice,
)
from src.config.config import global_config


@pytest.mark.asyncio
async def test_unsupported_provider_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 不认识时必须抛配置错误，而不是静默返回 None。"""

    monkeypatch.setattr(global_config.voice, "enable_tts", True)
    monkeypatch.setattr(global_config.voice, "tts_provider", "some_unknown_tts")

    with pytest.raises(TtsConfigurationError) as exc_info:
        await synthesize_voice("你好")

    assert "some_unknown_tts" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_reference_audio_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """参考音频为空同样属于配置错误，必须走降级而不是丢弃消息。"""

    monkeypatch.setattr(global_config.voice, "enable_tts", True)
    monkeypatch.setattr(global_config.voice, "tts_provider", "gpt_sovits")
    monkeypatch.setattr(global_config.voice, "tts_ref_audio_path", "   ")

    with pytest.raises(TtsConfigurationError):
        await synthesize_voice("你好")


@pytest.mark.asyncio
async def test_disabled_tts_returns_none_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """语音功能关闭是正常路径，返回 None 表示本次无需合成。"""

    monkeypatch.setattr(global_config.voice, "enable_tts", False)

    assert await synthesize_voice("你好") is None


@pytest.mark.asyncio
async def test_configuration_error_degrades_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置不可用时 convert_text_message_to_voice 必须返回 True 继续发文本。"""

    monkeypatch.setattr(global_config.voice, "enable_tts", True)
    monkeypatch.setattr(global_config.voice, "tts_provider", "some_unknown_tts")
    monkeypatch.setattr(global_config.voice, "tts_only_when_requested", False)
    monkeypatch.setattr(global_config.voice, "tts_send_probability", 1.0)

    class _TextComponent:
        def __init__(self, text: str) -> None:
            self.text = text

    class _RawMessage:
        def __init__(self, text: str) -> None:
            self.components = [_TextComponent(text)]

    class _Message:
        def __init__(self, text: str) -> None:
            self.session_id = ""
            self.processed_plain_text = text
            self.raw_message = _RawMessage(text)

    message = _Message("这是一条应该降级为文本的回复")

    # 配置错误被内部消化成"继续发文本"，不会把异常抛给发送链路。
    assert await convert_text_message_to_voice(message) is True  # type: ignore[arg-type]
    # 组件未被改写，文本仍然保留。
    assert message.raw_message.components[0].text == "这是一条应该降级为文本的回复"


def test_prepare_tts_text_truncates_to_configured_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """超长文本按配置截断，且不会残留尾部空白。"""

    monkeypatch.setattr(global_config.voice, "tts_max_text_length", 5)

    assert prepare_tts_text("一二三四五六七八九") == "一二三四五"
    assert prepare_tts_text("  你好   世界  ") == "你好 世界"


def test_extract_private_dialogue_keeps_only_quoted_lines() -> None:
    """私密模式只朗读引号中的台词，环境描写留在文字里。"""

    reply = "（她抬头看向窗外）\n“今天天气真好呢。”\n雨声淅淅沥沥。"

    assert extract_private_dialogue_tts_text(reply) == "今天天气真好呢。"


def test_extract_private_dialogue_strips_stage_directions_without_quotes() -> None:
    """没有引号时退化为逐行剥离舞台提示与旁白。"""

    reply = "旁白：房间很安静。\n千惠：我回来了。\n*轻轻关上门*"

    assert extract_private_dialogue_tts_text(reply) == "我回来了。"
