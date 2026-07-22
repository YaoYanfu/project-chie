"""云端 Project Chie 桥接客户端。"""

from typing import Any, Dict, Optional

import httpx

from .settings import AmadeusSettings


class RemoteMaiBotClient:
    """仅通过 Amadeus 独立 token 访问云端桥接 API。"""

    def __init__(self, settings: AmadeusSettings, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._settings = settings
        self._transport = transport

    async def get_status(self) -> Dict[str, Any]:
        return await self._get("/api/webui/amadeus/bridge/status")

    async def get_identity(self) -> Dict[str, Any]:
        config = self._settings.load()
        person_id = config["owner_person_id"]
        if not person_id:
            return {"configured": False, "mapped": False, "reason": "尚未配置 owner_person_id"}
        result = await self._get(f"/api/webui/amadeus/bridge/identity/{person_id}")
        result["configured"] = True
        return result

    async def _get(self, path: str) -> Dict[str, Any]:
        config = self._settings.load()
        base_url = config["remote_base_url"]
        token = config["remote_token"]
        if not base_url or not token:
            return {"configured": False, "online": False, "reason": "尚未配置云端地址或独立 token"}

        try:
            async with httpx.AsyncClient(timeout=4.0, transport=self._transport) as client:
                response = await client.get(
                    f"{base_url}{path}",
                    headers={"X-Amadeus-Token": token},
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("云端返回格式错误")
            payload["configured"] = True
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "configured": True,
                "online": False,
                "reason": str(exc),
            }
