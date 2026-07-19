"""Postgres repository for strategy backtest run history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BacktestRunRow

# Keep in sync with StrategiesRepository.ASSET_CLASS_LABELS (avoid circular import).
_ASSET_CLASS_LABELS: dict[str, str] = {
    "forex": "Forex",
    "metals": "Precious Metals",
    "stocks": "Stocks",
    "crypto": "Crypto",
    "futures": "Futures",
    "options": "Options",
}

BACKTEST_RUN_STATUS_QUEUED = "queued"
BACKTEST_RUN_STATUS_RUNNING = "running"
BACKTEST_RUN_STATUS_COMPLETED = "completed"
BACKTEST_RUN_STATUS_FAILED = "failed"

BACKTEST_RUN_STATUSES = frozenset(
    {
        BACKTEST_RUN_STATUS_QUEUED,
        BACKTEST_RUN_STATUS_RUNNING,
        BACKTEST_RUN_STATUS_COMPLETED,
        BACKTEST_RUN_STATUS_FAILED,
    }
)


def normalize_backtest_run_status(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_RUN_STATUSES:
        return raw.strip()
    return BACKTEST_RUN_STATUS_QUEUED


def empty_backtest_stats() -> dict[str, Any]:
    return {
        "total_trades": None,
        "win_rate": None,
        "realized_pnl": None,
        "max_drawdown": None,
    }


def normalize_backtest_stats(raw: dict[str, Any] | None) -> dict[str, Any]:
    stats = empty_backtest_stats()
    if not raw:
        return stats

    total_trades = raw.get("total_trades")
    win_rate = raw.get("win_rate")
    realized_pnl = raw.get("realized_pnl")
    max_drawdown = raw.get("max_drawdown")

    stats.update(
        {
            "total_trades": int(total_trades) if total_trades is not None else None,
            "win_rate": float(win_rate) if win_rate is not None else None,
            "realized_pnl": float(realized_pnl) if realized_pnl is not None else None,
            "max_drawdown": float(max_drawdown) if max_drawdown is not None else None,
        }
    )
    return stats


def _parse_instant(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def serialize_backtest_run(doc: dict[str, Any]) -> dict[str, Any]:
    asset_class = str(doc.get("asset_class") or "")
    return {
        "id": doc["id"],
        "strategy_id": doc.get("strategy_id") or "",
        "strategy_name": doc.get("strategy_name") or "",
        "asset_class": asset_class,
        "asset_class_label": _ASSET_CLASS_LABELS.get(
            asset_class, asset_class.title() if asset_class else ""
        ),
        "timeframe": doc.get("timeframe"),
        "instruments": list(doc.get("instruments") or []),
        "status": normalize_backtest_run_status(doc.get("status")),
        "created_at": doc.get("created_at"),
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
        "error": doc.get("error"),
        "stats": normalize_backtest_stats(doc.get("stats")),
        "params_snapshot": doc.get("params_snapshot"),
    }


def build_queued_run_document(strategy: dict[str, Any]) -> dict[str, Any]:
    """Build a denormalized queued run document from a serialized strategy."""
    params = strategy.get("params") or {}
    timeframe = strategy.get("timeframe") or params.get("timeframe")
    created_at = _now_iso()
    return {
        "id": str(uuid4()),
        "strategy_id": strategy["id"],
        "strategy_name": strategy.get("name") or "",
        "asset_class": strategy.get("asset_class") or "",
        "timeframe": timeframe,
        "instruments": list(strategy.get("instruments") or []),
        "status": BACKTEST_RUN_STATUS_QUEUED,
        "created_at": created_at,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "stats": empty_backtest_stats(),
        "params_snapshot": dict(params) if params else None,
    }


def _sync_row_columns(row: BacktestRunRow, doc: dict[str, Any]) -> None:
    row.strategy_id = str(doc.get("strategy_id") or "")
    row.status = normalize_backtest_run_status(doc.get("status"))
    created = _parse_instant(doc.get("created_at")) or _now_utc()
    row.created_at = created
    row.doc = doc


class BacktestRunsRepository:
    """Postgres-backed backtest run history (`brokerai.backtest_runs`)."""

    COLLECTION = "backtest_runs"

    async def create_queued_runs(self, strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Persist one queued run per strategy. Returns serialized run documents."""
        if not strategies:
            return []

        created: list[dict[str, Any]] = []
        async with session_scope() as session:
            for strategy in strategies:
                if not strategy.get("id"):
                    continue
                doc = build_queued_run_document(strategy)
                row = BacktestRunRow(id=doc["id"], doc=doc)
                _sync_row_columns(row, doc)
                session.add(row)
                created.append(serialize_backtest_run(doc))
        return created

    async def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(BacktestRunRow)
            if strategy_id:
                stmt = stmt.where(BacktestRunRow.strategy_id == strategy_id)
            if status and status in BACKTEST_RUN_STATUSES:
                stmt = stmt.where(BacktestRunRow.status == status)
            if before is not None:
                when = (
                    before.astimezone(timezone.utc)
                    if before.tzinfo
                    else before.replace(tzinfo=timezone.utc)
                )
                stmt = stmt.where(BacktestRunRow.created_at < when)
            stmt = stmt.order_by(BacktestRunRow.created_at.desc()).limit(max(1, min(limit, 200)))
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_backtest_run(dict(row.doc)) for row in rows]

    async def get_by_id(self, run_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            return serialize_backtest_run(dict(row.doc))

    async def delete_by_id(self, run_id: str) -> bool:
        async with session_scope() as session:
            result = await session.execute(
                delete(BacktestRunRow).where(BacktestRunRow.id == run_id)
            )
            return bool(result.rowcount)
