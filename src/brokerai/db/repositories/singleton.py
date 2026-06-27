from __future__ import annotations

from typing import Any

from brokerai.db.client import get_db


async def get_singleton_doc(
    collection: str,
    *,
    match: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    handle = await get_db()
    doc = await handle.db[collection].find_one(match, {"_id": 0})
    if doc:
        return doc
    return defaults.copy()


async def upsert_singleton_doc(
    collection: str,
    *,
    match: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    handle = await get_db()
    await handle.db[collection].update_one(match, {"$set": document}, upsert=True)
    return document
