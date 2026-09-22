"""PostgreSQL 连接池 + schema 初始化。"""
import json
import pathlib

import asyncpg

from . import config

_pool: asyncpg.Pool | None = None
_SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "schema.sql"


async def _init_conn(conn: asyncpg.Connection) -> None:
    # jsonb 列可直接传 dict/list（自动序列化/反序列化）
    for typ in ("json", "jsonb"):
        await conn.set_type_codec(
            typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            config.DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=10,
            init=_init_conn,
        )
    return _pool


async def init_schema() -> None:
    pool = await get_pool()
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)
    from . import users
    await users.seed_users(pool)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
