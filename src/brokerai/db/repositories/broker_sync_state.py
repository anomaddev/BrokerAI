from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BrokerSyncStateRow


def _default_lock_holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _parse_doc_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _lock_available(doc: dict[str, Any], now: datetime, lock_holder: str) -> bool:
    holder = doc.get("sync_lock_holder")
    expires = _parse_doc_time(doc.get("sync_lock_expires_at"))
    if not holder:
        return True
    if expires is not None and expires <= now:
        return True
    return holder == lock_holder


class BrokerSyncStateRepository:
    COLLECTION = "broker_sync_state"

    async def _get_row(
        self,
        session,
        exchange_id: str,
        account_id: str,
    ) -> BrokerSyncStateRow | None:
        stmt = select(BrokerSyncStateRow).where(
            BrokerSyncStateRow.exchange_id == exchange_id,
            BrokerSyncStateRow.account_id == account_id,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_state(self, exchange_id: str, account_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await self._get_row(session, exchange_id, account_id)
            return dict(row.doc) if row else None

    async def get_cursor(self, exchange_id: str, account_id: str) -> str | None:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return None
        cursor = doc.get("sync_cursor")
        return str(cursor) if cursor else None

    async def get_last_sync_at(self, exchange_id: str, account_id: str) -> datetime | None:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return None
        return _parse_doc_time(doc.get("last_sync_at"))

    async def reset_state(self, exchange_id: str, account_id: str) -> None:
        """Clear sync cursor and bootstrap markers (account/credential switch)."""
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = await self._get_row(session, exchange_id, account_id)
            if row is None:
                doc = {
                    "exchange_id": exchange_id,
                    "account_id": account_id,
                    "updated_at": now,
                }
                session.add(
                    BrokerSyncStateRow(
                        exchange_id=exchange_id,
                        account_id=account_id,
                        doc=doc,
                    )
                )
            else:
                doc = dict(row.doc)
                doc["updated_at"] = now
                for key in ("sync_cursor", "account_bootstrap_at", "last_sync_error"):
                    doc.pop(key, None)
                row.doc = doc

    async def try_acquire_sync_lock(
        self,
        exchange_id: str,
        account_id: str,
        *,
        holder: str | None = None,
        ttl_seconds: int = 90,
    ) -> bool:
        """Acquire a distributed lease for OANDA account polling."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(30, ttl_seconds))
        lock_holder = holder or _default_lock_holder()
        lock_set = {
            "sync_lock_holder": lock_holder,
            "sync_lock_expires_at": expires_at,
            "updated_at": now,
        }

        for _attempt in range(2):
            try:
                async with session_scope() as session:
                    row = await self._get_row(session, exchange_id, account_id)
                    if row is not None and _lock_available(dict(row.doc), now, lock_holder):
                        doc = dict(row.doc)
                        doc.update(lock_set)
                        row.doc = doc
                        return True

                    if row is None:
                        doc = {
                            "exchange_id": exchange_id,
                            "account_id": account_id,
                            **lock_set,
                            "created_at": now,
                        }
                        session.add(
                            BrokerSyncStateRow(
                                exchange_id=exchange_id,
                                account_id=account_id,
                                doc=doc,
                            )
                        )
                        return True

                    return False
            except IntegrityError:
                continue
        return False

    async def release_sync_lock(
        self,
        exchange_id: str,
        account_id: str,
        *,
        holder: str | None = None,
    ) -> None:
        lock_holder = holder or _default_lock_holder()
        async with session_scope() as session:
            row = await self._get_row(session, exchange_id, account_id)
            if row is None:
                return
            doc = dict(row.doc)
            if doc.get("sync_lock_holder") != lock_holder:
                return
            doc.pop("sync_lock_holder", None)
            doc.pop("sync_lock_expires_at", None)
            doc["updated_at"] = datetime.now(timezone.utc)
            row.doc = doc

    async def set_state(
        self,
        exchange_id: str,
        account_id: str,
        *,
        sync_cursor: str | None = None,
        last_sync_at: datetime | None = None,
        environment: str | None = None,
        account_bootstrap_at: datetime | None = None,
        last_sync_error: str | None = None,
        clear_last_sync_error: bool = False,
        last_exposure_check_at: datetime | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        updates: dict[str, Any] = {"updated_at": now, "last_sync_at": last_sync_at or now}
        if sync_cursor is not None:
            updates["sync_cursor"] = sync_cursor
        if environment is not None:
            updates["environment"] = environment
        if account_bootstrap_at is not None:
            updates["account_bootstrap_at"] = account_bootstrap_at
        if last_exposure_check_at is not None:
            updates["last_exposure_check_at"] = last_exposure_check_at
        if last_sync_error is not None:
            updates["last_sync_error"] = last_sync_error

        async with session_scope() as session:
            row = await self._get_row(session, exchange_id, account_id)
            if row is None:
                doc = {
                    "exchange_id": exchange_id,
                    "account_id": account_id,
                    "created_at": now,
                    **updates,
                }
                session.add(
                    BrokerSyncStateRow(
                        exchange_id=exchange_id,
                        account_id=account_id,
                        doc=doc,
                    )
                )
            else:
                doc = dict(row.doc)
                doc.update(updates)
                if clear_last_sync_error:
                    doc.pop("last_sync_error", None)
                row.doc = doc

    async def needs_environment_reset(
        self,
        exchange_id: str,
        account_id: str,
        *,
        environment: str,
    ) -> bool:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return False
        stored_env = str(doc.get("environment") or "")
        return bool(stored_env and stored_env != environment)
