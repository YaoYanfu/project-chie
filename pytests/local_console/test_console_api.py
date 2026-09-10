"""私密控制台 API 测试。

覆盖两个关键契约：
1. `/api/status` 必须暴露 `voice_timeout`，前端据此推导等待台词语音的轮询预算；
2. 未携带令牌的请求必须被拒绝，且认证失败不能泄漏状态信息。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from src.config.config import global_config
from src.local_console.app import create_app
from src.local_console.settings import LocalConsoleSettings

_TEST_TOKEN = "test-local-console-token"


def _build_client(tmp_path: Path) -> TestClient:
    """构造一个不调用本地模型的私密控制台，避免测试期间访问 Ollama。"""

    settings = LocalConsoleSettings(
        access_token=_TEST_TOKEN,
        data_dir=tmp_path,
        # 占位适配器不发起任何 HTTP 请求，测试只关注 API 契约。
        model_enabled=False,
    )
    return TestClient(create_app(settings))


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_TOKEN}"}


def test_status_exposes_voice_timeout_aligned_with_tts_config(tmp_path: Path) -> None:
    """前端轮询预算依赖 voice_timeout，必须与配置里的 tts_timeout 一致。"""

    with _build_client(tmp_path) as client:
        response = client.get("/api/status", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["voice_timeout"] == global_config.voice.tts_timeout
    # 前端会用 timeout * 1000 作为毫秒预算，必须为正数才有意义。
    assert payload["voice_timeout"] > 0


def test_status_requires_token(tmp_path: Path) -> None:
    """缺失或错误的令牌都必须返回 401，且不得回显任何状态字段。"""

    with _build_client(tmp_path) as client:
        without_token = client.get("/api/status")
        wrong_token = client.get("/api/status", headers={"Authorization": "Bearer wrong-token"})

    assert without_token.status_code == 401
    assert wrong_token.status_code == 401
    assert "voice_timeout" not in without_token.json()


def test_health_endpoint_stays_public(tmp_path: Path) -> None:
    """健康检查是唯一免鉴权端点，供启动脚本探测就绪状态。"""

    with _build_client(tmp_path) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_rejects_empty_message(tmp_path: Path) -> None:
    """空白消息必须在进入引擎之前被拒绝。"""

    with _build_client(tmp_path) as client:
        response = client.post("/api/chat", headers=_auth_headers(), json={"message": "   "})

    assert response.status_code == 400
