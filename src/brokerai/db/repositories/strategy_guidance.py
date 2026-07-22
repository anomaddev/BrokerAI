"""Strategy guidance rows materialised from research signals-snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import StrategyGuidanceRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyGuidanceRepository:
    async def upsert_from_signals_snapshot(self, snapshot: dict[str, Any]) -> int:
        """Write/replace guidance rows from a research signals-snapshot payload."""
        report_date = str(snapshot.get("report_date") or "")
        report_filename = str(snapshot.get("report_filename") or f"daily:{report_date}")
        source_type = "daily"
        source_key = report_filename
        written = 0
        asset_classes = snapshot.get("asset_classes") or []
        if not isinstance(asset_classes, list):
            return 0

        async with session_scope() as session:
            for block in asset_classes:
                if not isinstance(block, dict):
                    continue
                asset_class = str(block.get("asset_class") or "forex")
                items = block.get("items") or []
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    symbol = str(item.get("symbol") or "").strip()
                    if not symbol:
                        continue
                    status = str(item.get("status") or "ok")
                    doc = {
                        "source_type": source_type,
                        "source_key": source_key,
                        "as_of_date": report_date,
                        "asset_class": asset_class,
                        "symbol": symbol,
                        "status": status,
                        "signal": item.get("signal"),
                        "tone": item.get("tone"),
                        "approach": item.get("approach"),
                        "conviction": item.get("conviction"),
                        "report_date": report_date,
                        "generated_at": snapshot.get("generated_at"),
                    }
                    existing = (
                        await session.execute(
                            select(StrategyGuidanceRow).where(
                                StrategyGuidanceRow.source_type == source_type,
                                StrategyGuidanceRow.source_key == source_key,
                                StrategyGuidanceRow.symbol == symbol,
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        existing.doc = doc
                        existing.as_of_date = report_date
                        existing.status = status
                        existing.parsed_at = _now()
                    else:
                        session.add(
                            StrategyGuidanceRow(
                                id=uuid4().hex,
                                source_type=source_type,
                                source_key=source_key,
                                symbol=symbol,
                                as_of_date=report_date,
                                status=status,
                                parsed_at=_now(),
                                doc=doc,
                            )
                        )
                    written += 1
        return written

    async def get_for_symbol(self, symbol: str, *, as_of_date: str | None = None) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = select(StrategyGuidanceRow).where(StrategyGuidanceRow.symbol == symbol)
            if as_of_date:
                stmt = stmt.where(StrategyGuidanceRow.as_of_date == as_of_date)
            stmt = stmt.order_by(StrategyGuidanceRow.parsed_at.desc()).limit(1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return {"id": row.id, **dict(row.doc)}

    async def latest_for_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            row = await self.get_for_symbol(symbol)
            if row:
                out[symbol] = row
        return out
