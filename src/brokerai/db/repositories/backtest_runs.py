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
BACKTEST_RUN_STATUS_CANCELLED = "cancelled"

BACKTEST_RUN_STATUSES = frozenset(
    {
        BACKTEST_RUN_STATUS_QUEUED,
        BACKTEST_RUN_STATUS_RUNNING,
        BACKTEST_RUN_STATUS_COMPLETED,
        BACKTEST_RUN_STATUS_FAILED,
        BACKTEST_RUN_STATUS_CANCELLED,
    }
)

BACKTEST_RUN_TERMINAL_STATUSES = frozenset(
    {
        BACKTEST_RUN_STATUS_COMPLETED,
        BACKTEST_RUN_STATUS_FAILED,
        BACKTEST_RUN_STATUS_CANCELLED,
    }
)

BACKTEST_PERIODS = frozenset({"1m", "3m", "6m", "1y", "2y", "5y"})

DEFAULT_ACCOUNT_MARGIN = 10_000.0
MIN_ACCOUNT_MARGIN = 100.0
MAX_ACCOUNT_MARGIN = 50_000_000.0


def normalize_backtest_run_status(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_RUN_STATUSES:
        return raw.strip()
    return BACKTEST_RUN_STATUS_QUEUED


def normalize_backtest_period(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_PERIODS:
        return raw.strip()
    return "6m"


def normalize_account_margin(raw: Any) -> float:
    """Clamp available account margin to ``[$100, $50M]``; default ``$10_000``."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_ACCOUNT_MARGIN
    if value != value:  # NaN
        return DEFAULT_ACCOUNT_MARGIN
    return max(MIN_ACCOUNT_MARGIN, min(MAX_ACCOUNT_MARGIN, value))


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


def _serialize_ai_feedback(raw: Any) -> dict[str, Any] | None:
    """Lazy import to avoid circular deps with the backtesting package."""
    from brokerai.backtesting.ai_feedback import normalize_ai_feedback

    if not isinstance(raw, dict):
        return None
    return normalize_ai_feedback(raw)


def serialize_backtest_run(doc: dict[str, Any], *, row: BacktestRunRow | None = None) -> dict[str, Any]:
    asset_class = str(doc.get("asset_class") or "")
    progress_pct = float(row.progress_pct) if row is not None else float(doc.get("progress_pct") or 0)
    current_bar = None
    if row is not None and row.current_bar is not None:
        current_bar = row.current_bar.astimezone(timezone.utc).isoformat()
    elif doc.get("current_bar"):
        current_bar = str(doc.get("current_bar"))
    status_message = (
        row.status_message
        if row is not None and row.status_message is not None
        else doc.get("status_message")
    )
    cancel_requested = (
        bool(row.cancel_requested)
        if row is not None
        else bool(doc.get("cancel_requested", False))
    )
    return {
        "id": doc["id"],
        "name": doc.get("name") or "",
        "strategy_id": doc.get("strategy_id") or "",
        "strategy_name": doc.get("strategy_name") or "",
        "asset_class": asset_class,
        "asset_class_label": _ASSET_CLASS_LABELS.get(
            asset_class, asset_class.title() if asset_class else ""
        ),
        "timeframe": doc.get("timeframe"),
        "instruments": list(doc.get("instruments") or []),
        "instrument": doc.get("instrument") or (list(doc.get("instruments") or [])[:1] or [None])[0],
        "period": normalize_backtest_period(doc.get("period")),
        "period_start": doc.get("period_start"),
        "period_end": doc.get("period_end"),
        "account_margin": normalize_account_margin(doc.get("account_margin")),
        "verbose": bool(doc.get("verbose", False)),
        "status": normalize_backtest_run_status(doc.get("status")),
        "progress_pct": progress_pct,
        "current_bar": current_bar,
        "status_message": status_message,
        "cancel_requested": cancel_requested,
        "created_at": doc.get("created_at"),
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
        "error": doc.get("error"),
        "stats": normalize_backtest_stats(doc.get("stats")),
        "equity_curve": list(doc.get("equity_curve") or []),
        "params_snapshot": doc.get("params_snapshot"),
        "ai_feedback": _serialize_ai_feedback(doc.get("ai_feedback")),
    }


def build_queued_run_document(
    strategy: dict[str, Any],
    *,
    name: str | None = None,
    instrument: str | None = None,
    period: str = "6m",
    verbose: bool = False,
    period_start: str | None = None,
    period_end: str | None = None,
    account_margin: float | None = None,
) -> dict[str, Any]:
    """Build a denormalized queued run document from a serialized strategy."""
    params = strategy.get("params") or {}
    timeframe = strategy.get("timeframe") or params.get("timeframe")
    instruments = list(strategy.get("instruments") or [])
    chosen = instrument or (instruments[0] if instruments else None)
    created_at = _now_iso()
    run_name = (name or "").strip() or f"{strategy.get('name') or 'Strategy'} backtest"
    return {
        "id": str(uuid4()),
        "name": run_name,
        "strategy_id": strategy["id"],
        "strategy_name": strategy.get("name") or "",
        "asset_class": strategy.get("asset_class") or "",
        "timeframe": timeframe,
        "instruments": instruments,
        "instrument": chosen,
        "period": normalize_backtest_period(period),
        "period_start": period_start,
        "period_end": period_end,
        "account_margin": normalize_account_margin(
            account_margin if account_margin is not None else DEFAULT_ACCOUNT_MARGIN
        ),
        "verbose": bool(verbose),
        "status": BACKTEST_RUN_STATUS_QUEUED,
        "progress_pct": 0.0,
        "current_bar": None,
        "status_message": None,
        "cancel_requested": False,
        "created_at": created_at,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "stats": empty_backtest_stats(),
        "equity_curve": [],
        "params_snapshot": dict(params) if params else None,
        "ai_feedback": None,
    }


def _sync_row_columns(row: BacktestRunRow, doc: dict[str, Any]) -> None:
    row.strategy_id = str(doc.get("strategy_id") or "")
    row.status = normalize_backtest_run_status(doc.get("status"))
    created = _parse_instant(doc.get("created_at")) or _now_utc()
    row.created_at = created
    row.progress_pct = float(doc.get("progress_pct") or 0)
    row.current_bar = _parse_instant(doc.get("current_bar"))
    message = doc.get("status_message")
    row.status_message = str(message) if message is not None else None
    row.cancel_requested = bool(doc.get("cancel_requested", False))
    row.doc = doc


class BacktestRunsRepository:
    """Postgres-backed backtest run history (`brokerai.backtest_runs`)."""

    COLLECTION = "backtest_runs"

    async def create_queued_runs(
        self,
        strategies: list[dict[str, Any]],
        *,
        name: str | None = None,
        instrument: str | None = None,
        period: str = "6m",
        verbose: bool = False,
        period_start: str | None = None,
        period_end: str | None = None,
        account_margin: float | None = None,
    ) -> list[dict[str, Any]]:
        """Persist one queued run per strategy. Returns serialized run documents."""
        if not strategies:
            return []

        created: list[dict[str, Any]] = []
        async with session_scope() as session:
            for strategy in strategies:
                if not strategy.get("id"):
                    continue
                doc = build_queued_run_document(
                    strategy,
                    name=name,
                    instrument=instrument,
                    period=period,
                    verbose=verbose,
                    period_start=period_start,
                    period_end=period_end,
                    account_margin=account_margin,
                )
                row = BacktestRunRow(id=doc["id"], doc=doc)
                _sync_row_columns(row, doc)
                session.add(row)
                created.append(serialize_backtest_run(doc, row=row))
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
            return [serialize_backtest_run(dict(row.doc), row=row) for row in rows]

    async def get_by_id(self, run_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            return serialize_backtest_run(dict(row.doc), row=row)

    async def get_raw_doc(self, run_id: str) -> dict[str, Any] | None:
        """Return the mutable document (includes fields omitted from API serialize)."""
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            doc = dict(row.doc)
            doc["progress_pct"] = float(row.progress_pct or 0)
            if row.current_bar is not None:
                doc["current_bar"] = row.current_bar.astimezone(timezone.utc).isoformat()
            doc["status_message"] = row.status_message
            doc["cancel_requested"] = bool(row.cancel_requested)
            doc["status"] = normalize_backtest_run_status(row.status)
            return doc

    async def delete_by_id(self, run_id: str) -> bool:
        async with session_scope() as session:
            result = await session.execute(
                delete(BacktestRunRow).where(BacktestRunRow.id == run_id)
            )
            return bool(result.rowcount)

    async def count_running(self) -> int:
        async with session_scope() as session:
            stmt = select(BacktestRunRow).where(
                BacktestRunRow.status == BACKTEST_RUN_STATUS_RUNNING
            )
            rows = (await session.execute(stmt)).scalars().all()
            return len(rows)

    async def claim_next_queued(self) -> dict[str, Any] | None:
        """Atomically claim the oldest queued run (auto-start path)."""
        async with session_scope() as session:
            stmt = (
                select(BacktestRunRow)
                .where(
                    BacktestRunRow.status == BACKTEST_RUN_STATUS_QUEUED,
                    BacktestRunRow.cancel_requested.is_(False),
                )
                .order_by(BacktestRunRow.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            try:
                row = (await session.execute(stmt)).scalars().first()
            except Exception:
                # SQLite tests lack FOR UPDATE SKIP LOCKED; fall back.
                stmt = (
                    select(BacktestRunRow)
                    .where(
                        BacktestRunRow.status == BACKTEST_RUN_STATUS_QUEUED,
                        BacktestRunRow.cancel_requested.is_(False),
                    )
                    .order_by(BacktestRunRow.created_at.asc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalars().first()
            if row is None:
                return None
            doc = dict(row.doc)
            started = _now_iso()
            doc["status"] = BACKTEST_RUN_STATUS_RUNNING
            doc["started_at"] = started
            doc["status_message"] = "Starting backtest"
            doc["progress_pct"] = 0.0
            _sync_row_columns(row, doc)
            return serialize_backtest_run(doc, row=row)

    async def mark_running(self, run_id: str) -> dict[str, Any] | None:
        """Manual start: transition a queued run to running."""
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            if normalize_backtest_run_status(row.status) != BACKTEST_RUN_STATUS_QUEUED:
                return serialize_backtest_run(dict(row.doc), row=row)
            if row.cancel_requested:
                return serialize_backtest_run(dict(row.doc), row=row)
            doc = dict(row.doc)
            doc["status"] = BACKTEST_RUN_STATUS_RUNNING
            doc["started_at"] = _now_iso()
            doc["status_message"] = "Starting backtest"
            doc["progress_pct"] = 0.0
            _sync_row_columns(row, doc)
            return serialize_backtest_run(doc, row=row)

    async def request_cancel(self, run_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            doc = dict(row.doc)
            status = normalize_backtest_run_status(row.status)
            if status in BACKTEST_RUN_TERMINAL_STATUSES:
                return serialize_backtest_run(doc, row=row)
            row.cancel_requested = True
            doc["cancel_requested"] = True
            if status == BACKTEST_RUN_STATUS_QUEUED:
                doc["status"] = BACKTEST_RUN_STATUS_CANCELLED
                doc["finished_at"] = _now_iso()
                doc["status_message"] = "Cancelled before start"
                _sync_row_columns(row, doc)
            else:
                doc["status_message"] = "Cancel requested"
                row.status_message = "Cancel requested"
                row.doc = doc
            return serialize_backtest_run(doc, row=row)

    async def is_cancel_requested(self, run_id: str) -> bool:
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return True
            return bool(row.cancel_requested)

    async def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float,
        current_bar: datetime | str | None = None,
        status_message: str | None = None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        """Persist progress fields (and optional live stats) for a running backtest.

        ``stats`` is written into ``doc`` so list/detail APIs can show Trades /
        Win Rate / Realized P/L while the worker is still mid-run.
        """
        bar_dt = _parse_instant(current_bar) if current_bar is not None else None
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return
            doc = dict(row.doc)
            pct = max(0.0, min(100.0, float(progress_pct)))
            doc["progress_pct"] = pct
            row.progress_pct = pct
            if bar_dt is not None:
                doc["current_bar"] = bar_dt.isoformat()
                row.current_bar = bar_dt
            if status_message is not None:
                doc["status_message"] = status_message
                row.status_message = status_message
            if stats is not None:
                doc["stats"] = normalize_backtest_stats(stats)
            row.doc = doc

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        error: str | None = None,
        stats: dict[str, Any] | None = None,
        equity_curve: list[dict[str, Any]] | None = None,
        status_message: str | None = None,
    ) -> dict[str, Any] | None:
        terminal = normalize_backtest_run_status(status)
        if terminal not in BACKTEST_RUN_TERMINAL_STATUSES:
            terminal = BACKTEST_RUN_STATUS_FAILED
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            doc = dict(row.doc)
            doc["status"] = terminal
            doc["finished_at"] = _now_iso()
            doc["error"] = error
            doc["progress_pct"] = 100.0 if terminal == BACKTEST_RUN_STATUS_COMPLETED else float(
                doc.get("progress_pct") or 0
            )
            if stats is not None:
                doc["stats"] = normalize_backtest_stats(stats)
            if equity_curve is not None:
                doc["equity_curve"] = list(equity_curve)
            if status_message is not None:
                doc["status_message"] = status_message
            elif terminal == BACKTEST_RUN_STATUS_COMPLETED:
                doc["status_message"] = "Completed"
            elif terminal == BACKTEST_RUN_STATUS_CANCELLED:
                doc["status_message"] = "Cancelled"
            elif terminal == BACKTEST_RUN_STATUS_FAILED:
                doc["status_message"] = "Failed"
            _sync_row_columns(row, doc)
            return serialize_backtest_run(doc, row=row)

    async def list_claimable_manual_starts(self) -> list[str]:
        """Return run ids marked running but not yet finished (coordinator pickup)."""
        async with session_scope() as session:
            stmt = select(BacktestRunRow.id).where(
                BacktestRunRow.status == BACKTEST_RUN_STATUS_RUNNING,
                BacktestRunRow.cancel_requested.is_(False),
            )
            return [str(rid) for rid in (await session.execute(stmt)).scalars().all()]

    async def update_ai_feedback(
        self,
        run_id: str,
        feedback: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Persist the latest AI feedback blob on the run document."""
        from brokerai.backtesting.ai_feedback import normalize_ai_feedback

        normalized = normalize_ai_feedback(feedback)
        if normalized is None:
            return await self.get_by_id(run_id)
        async with session_scope() as session:
            row = await session.get(BacktestRunRow, run_id)
            if row is None:
                return None
            doc = dict(row.doc)
            doc["ai_feedback"] = normalized
            row.doc = doc
            return serialize_backtest_run(doc, row=row)
