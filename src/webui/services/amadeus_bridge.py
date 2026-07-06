"""云端 Amadeus 桥接 token 管理。"""

from pathlib import Path
from threading import RLock
from typing import Optional

import json
import secrets


class AmadeusBridgeTokenManager:
    """保存独立于 WebUI 管理 token 的 Amadeus 桥接 token。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parents[3] / "data" / "amadeus" / "bridge.json"
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def get_token(self) -> str:
        with self._lock:
            try:
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
                token = str(payload.get("token") or "")
            except (OSError, json.JSONDecodeError):
                token = ""
            if token:
                return token
            return self.rotate_token()

    def rotate_token(self) -> str:
        token = secrets.token_hex(32)
        with self._lock:
            temp_path = self.config_path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps({"token": token}, indent=2), encoding="utf-8")
            temp_path.replace(self.config_path)
        return token

    def verify(self, candidate: str) -> bool:
        return bool(candidate) and secrets.compare_digest(self.get_token(), candidate)


_manager: Optional[AmadeusBridgeTokenManager] = None


def get_amadeus_bridge_token_manager() -> AmadeusBridgeTokenManager:
    global _manager
    if _manager is None:
        _manager = AmadeusBridgeTokenManager()
    return _manager
