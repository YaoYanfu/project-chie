"""Amadeus 本机服务启动入口。"""

from argparse import ArgumentParser, Namespace
from typing import List, Optional

import uvicorn

from src.common.logger import get_logger, initialize_logging
from src.common.utils.port_checker import assert_port_available

from .app import create_app

logger = get_logger("amadeus.server")


def _parse_args(argv: Optional[List[str]] = None) -> Namespace:
    parser = ArgumentParser(description="启动 Amadeus 本机交互与控制中枢")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    host = "127.0.0.1"
    initialize_logging(verbose=False)
    assert_port_available(
        host=host,
        port=args.port,
        service_name="Amadeus 本机服务",
        logger=logger,
        config_hint="--port",
        allow_reuse_addr=True,
    )
    logger.info(f"Amadeus 本机服务启动: http://{host}:{args.port}")
    uvicorn.run(create_app(), host=host, port=args.port, log_config=None, access_log=False)
