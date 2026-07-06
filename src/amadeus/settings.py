"""Amadeus 本机配置存储。"""

from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional

import json
import os


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class AmadeusSettings:
    """管理 Amadeus 本机配置，并以原子方式保存。"""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or _project_root() / "data" / "amadeus"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self.tts_pid_path = self.data_dir / "tts.pid"
        self._lock = RLock()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            try:
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}

        return {
            "remote_base_url": os.getenv("AMADEUS_REMOTE_BASE_URL", str(payload.get("remote_base_url") or "")),
            "remote_token": os.getenv("AMADEUS_REMOTE_TOKEN", str(payload.get("remote_token") or "")),
            "owner_person_id": os.getenv("AMADEUS_OWNER_PERSON_ID", str(payload.get("owner_person_id") or "")),
        }

    def update_remote(self, remote_base_url: str, remote_token: str, owner_person_id: str) -> None:
        payload = {
            "remote_base_url": remote_base_url.rstrip("/"),
            "remote_token": remote_token,
            "owner_person_id": owner_person_id,
        }
        with self._lock:
            temp_path = self.config_path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self.config_path)

    @property
    def project_root(self) -> Path:
        return _project_root()

    @property
    def tts_script_path(self) -> Path:
        return self.project_root / "scripts" / "start_tts_server.ps1"
