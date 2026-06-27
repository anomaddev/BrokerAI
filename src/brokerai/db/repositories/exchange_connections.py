from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.db.repositories.ai_models import mask_api_key

OANDA_ID = "oanda"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExchangeConnectionsRepository:
    COLLECTION = "exchange_connections"

    async def get_oanda(self) -> dict[str, Any]:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"exchange_id": OANDA_ID}, {"_id": 0}
        )
        if doc:
            return doc
        return {
            "exchange_id": OANDA_ID,
            "access_token": "",
            "environment": "practice",
            "account_id": None,
        }

    async def save_oanda(
        self,
        *,
        access_token: str,
        environment: str,
        account_id: str | None,
    ) -> dict[str, Any]:
        doc = {
            "exchange_id": OANDA_ID,
            "access_token": access_token.strip(),
            "environment": environment,
            "account_id": account_id or None,
            "updated_at": _now_iso(),
        }
        handle = await get_db()
        await handle.db[self.COLLECTION].update_one(
            {"exchange_id": OANDA_ID},
            {"$set": doc},
            upsert=True,
        )
        return doc

    async def delete_oanda(self) -> bool:
        handle = await get_db()
        result = await handle.db[self.COLLECTION].delete_one({"exchange_id": OANDA_ID})
        return result.deleted_count > 0

    @staticmethod
    def public_oanda(doc: dict[str, Any]) -> dict[str, Any]:
        access_token = doc.get("access_token") or ""
        account_id = doc.get("account_id")
        return {
            "exchange_id": OANDA_ID,
            "environment": doc.get("environment") or "practice",
            "account_id": account_id,
            "access_token": mask_api_key(access_token or None),
            "access_token_set": bool(access_token),
            "connected": bool(access_token and account_id),
        }
