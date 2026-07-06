"""本机 GPT-SoVITS 服务管理。"""

from typing import Any, Dict

import os
import socket
import subprocess

import psutil

from .settings import AmadeusSettings
from .storage import AmadeusStore


class TtsService:
    """启动并只停止由 Amadeus 管理的 GPT-SoVITS 进程。"""

    HOST = "127.0.0.1"
    PORT = 9880

    def __init__(self, settings: AmadeusSettings, store: AmadeusStore) -> None:
        self._settings = settings
        self._store = store

    def status(self) -> Dict[str, Any]:
        running = self._port_is_open()
        pid = self._read_managed_pid()
        managed = pid is not None and self._is_expected_process(pid)
        if pid is not None and not managed:
            self._remove_pid_file()
        state = "running" if running else ("starting" if managed else "stopped")
        return {
            "state": state,
            "running": running,
            "managed": managed,
            "pid": pid if managed else None,
            "host": self.HOST,
            "port": self.PORT,
        }

    def start(self) -> Dict[str, Any]:
        current = self.status()
        if current["running"]:
            return current

        script_path = self._settings.tts_script_path
        if not script_path.is_file():
            raise FileNotFoundError(f"TTS 启动脚本不存在: {script_path}")

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-Background",
                "-NoBrowser",
                "-PidFile",
                str(self._settings.tts_pid_path),
            ],
            cwd=self._settings.project_root,
            creationflags=creation_flags,
        )
        self._store.add_event("local.tts", "service.start_requested", "已请求启动语音服务")
        return {
            "state": "starting",
            "running": False,
            "managed": False,
            "pid": None,
            "host": self.HOST,
            "port": self.PORT,
        }

    def stop(self) -> Dict[str, Any]:
        current = self.status()
        if not current["running"] and not current["managed"]:
            return current
        if not current["managed"] or current["pid"] is None:
            raise PermissionError("端口上的语音服务并非由 Amadeus 启动，拒绝结束未知进程")

        process = psutil.Process(int(current["pid"]))
        process.terminate()
        try:
            process.wait(timeout=8)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        self._remove_pid_file()
        self._store.add_event("local.tts", "service.stopped", "语音服务已停止")
        return self.status()

    def _port_is_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((self.HOST, self.PORT)) == 0

    def _read_managed_pid(self) -> int | None:
        try:
            return int(self._settings.tts_pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_expected_process(pid: int) -> bool:
        try:
            process = psutil.Process(pid)
            command_line = " ".join(process.cmdline()).lower()
            return process.is_running() and "api_v2.py" in command_line
        except (psutil.Error, OSError):
            return False

    def _remove_pid_file(self) -> None:
        try:
            self._settings.tts_pid_path.unlink()
        except FileNotFoundError:
            pass
