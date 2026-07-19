from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import ExchangeConnectionRow
from brokerai.db.repositories.ai_models import mask_api_key
from brokerai.integrations.oanda_client import normalize_access_token

OANDA_ID = "oanda"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExchangeConnectionsRepository:
    COLLECTION = "exchange_connections"

    async def get_connection(self, exchange_id: str) -> dict[str, Any]:
        """Return stored credentials for *exchange_id* (empty defaults when missing)."""
        async with session_scope() as session:
            row = await session.get(ExchangeConnectionRow, exchange_id)
            if row:
                return dict(row.doc)
        if exchange_id == OANDA_ID:
            return {
                "exchange_id": OANDA_ID,
                "access_token": "",
                "environment": "practice",
                "account_id": None,
            }
        return {"exchange_id": exchange_id}

    async def save_connection(self, exchange_id: str, **fields: Any) -> dict[str, Any]:
        """Upsert connection fields for *exchange_id*."""
        doc = {"exchange_id": exchange_id, "updated_at": _now_iso(), **fields}
        async with session_scope() as session:
            row = await session.get(ExchangeConnectionRow, exchange_id)
            if row is None:
                session.add(ExchangeConnectionRow(exchange_id=exchange_id, doc=doc))
            else:
                merged = dict(row.doc)
                merged.update(doc)
                row.doc = merged
                doc = merged
        return doc

    async def delete_connection(self, exchange_id: str) -> bool:
        async with session_scope() as session:
            result = await session.execute(
                delete(ExchangeConnectionRow).where(
                    ExchangeConnectionRow.exchange_id == exchange_id
                )
            )
            return bool(result.rowcount)

    async def get_oanda(self) -> dict[str, Any]:
        return await self.get_connection(OANDA_ID)

    async def save_oanda(
        self,
        *,
        access_token: str,
        environment: str,
        account_id: str | None,
    ) -> dict[str, Any]:
        return await self.save_connection(
            OANDA_ID,
            access_token=normalize_access_token(access_token),
            environment=environment,
            account_id=account_id or None,
        )

    async def delete_oanda(self) -> bool:
        return await self.delete_connection(OANDA_ID)

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
