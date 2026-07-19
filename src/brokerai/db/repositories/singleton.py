from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select

from brokerai.db.pg.client import session_scope

T = TypeVar("T")


def _apply_match(stmt, model: type[T], match: dict[str, Any]):
    for key, value in match.items():
        col = getattr(model, key)
        if value is None:
            stmt = stmt.where(col.is_(None))
        else:
            stmt = stmt.where(col == value)
    return stmt


async def get_singleton_doc(
    model: type[T],
    *,
    match: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    async with session_scope() as session:
        stmt = _apply_match(select(model), model, match)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return dict(row.doc)
    return defaults.copy()


async def upsert_singleton_doc(
    model: type[T],
    *,
    match: dict[str, Any],
    document: dict[str, Any],
    denormalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with session_scope() as session:
        stmt = _apply_match(select(model), model, match)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            attrs = {**match, **(denormalized or {}), "doc": document}
            session.add(model(**attrs))
        else:
            row.doc = document
            if denormalized:
                for key, value in denormalized.items():
                    setattr(row, key, value)
    return document
