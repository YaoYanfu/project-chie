from types import SimpleNamespace

import pytest

from src.core.tooling import ToolExecutionResult, ToolInvocation
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.reasoning_engine import MaisakaReasoningEngine


@pytest.mark.asyncio
async def test_successful_reply_pauses_internal_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeToolRegistry:
        async def list_tools(self, availability_context: object) -> list[object]:
            del availability_context
            return []

        async def invoke(
            self,
            invocation: ToolInvocation,
            execution_context: object,
        ) -> ToolExecutionResult:
            del execution_context
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=True,
                content="回复已生成并发送。",
            )

    runtime = SimpleNamespace(
        _tool_registry=FakeToolRegistry(),
        _update_stage_status=lambda *args, **kwargs: None,
        _reset_consecutive_wait_count=lambda reason: None,
        is_action_tool_currently_available=lambda tool_name: tool_name == "reply",
        log_prefix="[test]",
    )
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]

    async def _skip_record(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(engine, "_build_tool_execution_context", lambda latest_thought: object())
    monkeypatch.setattr(engine, "_build_tool_availability_context", lambda: object())
    monkeypatch.setattr(engine, "_log_tool_call_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        engine,
        "_build_tool_invocation",
        lambda tool_call, latest_thought: ToolInvocation(
            tool_name=tool_call.func_name,
            call_id=tool_call.call_id,
        ),
    )
    monkeypatch.setattr(engine, "_record_tool_execution_effects", _skip_record)
    monkeypatch.setattr(engine, "_append_tool_execution_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine, "_append_tool_display_results", lambda **kwargs: None)
    monkeypatch.setattr(engine, "_append_tool_post_history_messages", lambda messages: None)

    should_pause, pause_tool, _, _ = await engine._handle_tool_calls(
        [ToolCall(call_id="reply-call", func_name="reply", args={"msg_id": "m1"})],
        "应该回复用户这一条消息。",
    )

    assert should_pause is True
    assert pause_tool == "reply"
