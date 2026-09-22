"""events 表过期清理：按 event_type 分批删除，避免长事务锁表 / WAL 暴增。

作为 FastAPI lifespan 里的后台任务运行（app/main.py 挂起），每 INTERVAL_SECONDS 跑一轮。
删除用 (event_type, event_ts) 索引定位（schema.sql 的 idx_events_type_ts），
每批 BATCH_SIZE 行、批间让出，不停机、不阻塞 ingest。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from . import config
from .db import get_pool

log = logging.getLogger("cleanup")

BATCH_SIZE = 10_000        # 每批删除行数
INTERVAL_SECONDS = 6 * 3600  # 每 6 小时一轮
_YIELD_SECONDS = 0.1       # 批间让出，避免持续占用连接/CPU


async def cleanup_once() -> dict[str, int]:
    """对每个 event_type 分批删除早于保留期的 events，返回各类型删除行数。"""
    pool = await get_pool()
    result: dict[str, int] = {}
    async with pool.acquire() as conn:
        for event_type, days in config.EVENT_RETENTION_DAYS.items():
            if days <= 0:
                continue  # 0 = 不清理
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted_total = 0
            while True:
                row = await conn.fetchrow(
                    """
                    WITH doomed AS (
                        SELECT event_id FROM events
                        WHERE event_type = $1 AND event_ts < $2
                        LIMIT $3
                    ), del AS (
                        DELETE FROM events
                        WHERE event_id IN (SELECT event_id FROM doomed)
                        RETURNING 1
                    )
                    SELECT count(*) AS n FROM del
                    """,
                    event_type,
                    cutoff,
                    BATCH_SIZE,
                )
                n = row["n"]
                deleted_total += n
                if n < BATCH_SIZE:
                    break
                await asyncio.sleep(_YIELD_SECONDS)
            result[event_type] = deleted_total
    return result


async def cleanup_loop() -> None:
    """后台循环：启动后稍等即跑第一轮，此后每 INTERVAL_SECONDS 一轮。"""
    await asyncio.sleep(5)  # 等 pool/schema 就绪（init_schema 已先行，保险起见）
    while True:
        try:
            deleted = await cleanup_once()
            if any(deleted.values()):
                log.info("events 过期清理完成: %s", deleted)
        except Exception:
            log.exception("events 清理异常（本轮跳过，下轮重试）")
        await asyncio.sleep(INTERVAL_SECONDS)
