"""本地控制台启动入口。"""

from argparse import ArgumentParser, Namespace
from typing import List, Optional

import uvicorn

from src.common.logger import get_logger, initialize_logging
from src.common.utils.port_checker import assert_port_available

from .app import create_app
from .settings import LocalConsoleSettings

logger = get_logger("local_console.server")


def _parse_args(argv: Optional[List[str]] = None) -> Namespace:
    parser = ArgumentParser(description="启动 MaiBot 本地控制台")
    parser.add_argument("--host", default=None, help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="监听端口，默认 7860")
    parser.add_argument("--base-url", default=None, help="Ollama 服务地址，默认 http://127.0.0.1:11434")
    parser.add_argument("--model", default=None, help="本地模型名称")
    parser.add_argument("--num-ctx", type=int, default=None, help="Ollama 上下文窗口，默认 2048")
    parser.add_argument("--token", default=None, help="访问令牌")
    thinking_group = parser.add_mutually_exclusive_group()
    thinking_group.add_argument(
        "--disable-thinking",
        dest="disable_thinking",
        action="store_true",
        help="请求模型直接输出正文，默认启用",
    )
    thinking_group.add_argument(
        "--enable-thinking",
        dest="disable_thinking",
        action="store_false",
        help="允许模型输出 thinking 模式",
    )
    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument("--enable-model", dest="model_enabled", action="store_true", help="启用本地模型调用")
    model_group.add_argument("--disable-model", dest="model_enabled", action="store_false", help="使用占位回复，不调用模型")
    parser.set_defaults(disable_thinking=None)
    parser.set_defaults(model_enabled=None)
    return parser.parse_args(argv)


def _build_display_url(settings: LocalConsoleSettings) -> str:
    host = settings.host
    if host == "0.0.0.0":
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{settings.port}/?token={settings.access_token}"


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    initialize_logging(verbose=False)
    settings = LocalConsoleSettings.from_env(
        host=args.host,
        port=args.port,
        base_url=args.base_url,
        model=args.model,
        access_token=args.token,
        context_window=args.num_ctx,
        disable_thinking=args.disable_thinking,
        model_enabled=args.model_enabled,
    )
    settings.validate_network_policy()
    assert_port_available(
        host=settings.host,
        port=settings.port,
        service_name="本地控制台",
        logger=logger,
        config_hint="--port 或 MAIBOT_LOCAL_CONSOLE_PORT",
        allow_reuse_addr=True,
    )

    logger.info("本地控制台启动中")
    logger.info(f"访问地址: {_build_display_url(settings)}")
    logger.info(
        f"模型状态: {'接口已启用' if settings.model_enabled else '占位模式'} / "
        f"{settings.model} / num_ctx={settings.context_window} / "
        f"{'no_think' if settings.disable_thinking else 'thinking'}"
    )
    logger.info(f"会话数据目录: {settings.data_dir}")

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
