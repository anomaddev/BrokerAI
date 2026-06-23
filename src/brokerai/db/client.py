from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


class DatabaseHandle:
    def __init__(self, client: AsyncIOMotorClient, db: AsyncIOMotorDatabase) -> None:
        self.client = client
        self.db = db


async def get_db() -> DatabaseHandle:
    global _client, _db
    if _client is None or _db is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
        _db = _client[settings.mongodb_db]
    return DatabaseHandle(_client, _db)


async def ping_db() -> bool:
    try:
        handle = await get_db()
        await handle.client.admin.command("ping")
        return True
    except Exception:
        logger.debug("MongoDB ping failed", exc_info=True)
        return False


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None
