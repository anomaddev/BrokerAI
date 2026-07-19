from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import OandaAccountSummaryRow, OandaAccountsSnapshotRow
from brokerai.db.repositories.exchange_connections import OANDA_ID

SUMMARY_FIELDS = (
    "id",
    "alias",
    "currency",
    "balance",
    "nav",
    "unrealized_pl",
    "realized_pl",
    "margin_available",
    "margin_used",
    "open_trade_count",
    "open_position_count",
    "pending_order_count",
)


class OandaAccountSnapshotsRepository:
    """Persist OANDA account lists and time-series account summary snapshots."""

    ACCOUNTS_COLLECTION = "oanda_accounts_snapshots"
    SUMMARIES_COLLECTION = "oanda_account_summaries"

    async def upsert_accounts_snapshot(
        self,
        *,
        exchange_id: str = OANDA_ID,
        environment: str,
        accounts: list[dict[str, Any]],
        synced_at: datetime | None = None,
    ) -> None:
        """Store the latest accessible OANDA account list for *exchange_id*."""
        now = synced_at or datetime.now(timezone.utc)
        doc = {
            "exchange_id": exchange_id,
            "environment": environment,
            "accounts": accounts,
            "synced_at": now,
            "updated_at": now,
        }
        async with session_scope() as session:
            row = await session.get(OandaAccountsSnapshotRow, exchange_id)
            if row is None:
                doc["created_at"] = now
                session.add(OandaAccountsSnapshotRow(exchange_id=exchange_id, doc=doc))
            else:
                existing = dict(row.doc)
                doc["created_at"] = existing.get("created_at", now)
                row.doc = doc

    async def get_latest_accounts(self, *, exchange_id: str = OANDA_ID) -> dict[str, Any] | None:
        """Return the most recently synced OANDA account list document."""
        async with session_scope() as session:
            row = await session.get(OandaAccountsSnapshotRow, exchange_id)
            return dict(row.doc) if row else None

    async def insert_summary_snapshot(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
        environment: str,
        summary: dict[str, Any],
        synced_at: datetime | None = None,
    ) -> None:
        """Append one account summary snapshot for charting over time."""
        now = synced_at or datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "exchange_id": exchange_id,
            "account_id": account_id,
            "environment": environment,
            "synced_at": now,
        }
        for field in SUMMARY_FIELDS:
            if field in summary:
                doc[field] = summary[field]
        async with session_scope() as session:
            session.add(
                OandaAccountSummaryRow(
                    exchange_id=exchange_id,
                    account_id=account_id,
                    synced_at=now,
                    doc=doc,
                )
            )

    async def get_latest_summary(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
    ) -> dict[str, Any] | None:
        """Return the newest summary snapshot for *account_id*."""
        async with session_scope() as session:
            stmt = (
                select(OandaAccountSummaryRow)
                .where(
                    OandaAccountSummaryRow.exchange_id == exchange_id,
                    OandaAccountSummaryRow.account_id == account_id,
                )
                .order_by(OandaAccountSummaryRow.synced_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return dict(row.doc) if row else None

    async def list_summary_history(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """Return summary snapshots oldest-first for charting."""
        async with session_scope() as session:
            stmt = select(OandaAccountSummaryRow).where(
                OandaAccountSummaryRow.exchange_id == exchange_id,
                OandaAccountSummaryRow.account_id == account_id,
            )
            if since is not None:
                stmt = stmt.where(OandaAccountSummaryRow.synced_at >= since)
            if until is not None:
                stmt = stmt.where(OandaAccountSummaryRow.synced_at <= until)
            stmt = stmt.order_by(OandaAccountSummaryRow.synced_at.asc()).limit(
                max(1, min(limit, 10_000))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]

    @staticmethod
    def public_summary(doc: dict[str, Any]) -> dict[str, Any]:
        """Shape a stored summary document for API responses."""
        synced_at = doc.get("synced_at")
        payload: dict[str, Any] = {
            field: doc.get(field) for field in SUMMARY_FIELDS
        }
        payload["synced_at"] = synced_at.isoformat() if isinstance(synced_at, datetime) else synced_at
        payload["account_id"] = doc.get("account_id")
        payload["environment"] = doc.get("environment")
        return payload
