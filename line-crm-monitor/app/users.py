"""用户密码哈希、查询 + 初始化 seed（Stage7-E 权限底座）。

密码哈希用 stdlib pbkdf2_hmac，零新依赖；迭代 600000（OWASP 推荐，登录低频无性能压力）。
读侧鉴权依赖 _current_user 在 app/query.py（避免与 db 循环 import）。
"""
import hashlib
import hmac
import os

from . import config


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256，600000 次；格式 pbkdf2_sha256$iters$salt_hex$hash_hex。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return f"pbkdf2_sha256$600000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """常量时间比较校验密码；格式非法返回 False 而非抛异常。"""
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


async def get_user(username: str):
    """按用户名查用户；不存在返回 None（含 username/password_hash/role/group_id/is_active）。"""
    from .db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, password_hash, role, group_id, is_active "
            "FROM users WHERE username = $1",
            username,
        )
    return dict(row) if row else None


async def seed_users(pool) -> None:
    """幂等初始化（ON CONFLICT DO NOTHING，不覆盖已有数据）：

    1. 默认组 'default'（显示名「默认组」）
    2. admin 账号（env ADMIN_USERNAME / ADMIN_PASSWORD，缺一不创建）
    3. group 用户（env GROUP_USERS：{"用户名":{"password":"...","group_id":"default"}}）
    4. servers 归 default（防御性，schema 已 DEFAULT 'default'）
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO groups (id, name) VALUES ('default', '默认组') "
            "ON CONFLICT (id) DO NOTHING"
        )

        # 建组：GROUP_USERS 引用的 group_id + SERVER_GROUP_MAP 里出现的 group_id
        _group_ids = {
            str(meta.get("group_id"))
            for meta in (config.GROUP_USERS or {}).values()
            if isinstance(meta, dict) and meta.get("group_id")
        }
        _group_ids.update(str(g) for g in config.SERVER_GROUP_MAP.values() if g)
        for gid in _group_ids:
            if gid and gid != "default":
                await conn.execute(
                    "INSERT INTO groups (id, name) VALUES ($1, $1) "
                    "ON CONFLICT (id) DO NOTHING",
                    gid,
                )

        if config.ADMIN_USERNAME and config.ADMIN_PASSWORD:
            await conn.execute(
                "INSERT INTO users (username, password_hash, role, group_id) "
                "VALUES ($1, $2, 'admin', NULL) "
                "ON CONFLICT (username) DO NOTHING",
                config.ADMIN_USERNAME,
                hash_password(config.ADMIN_PASSWORD),
            )

        for username, meta in (config.GROUP_USERS or {}).items():
            if not isinstance(meta, dict):
                continue
            password = meta.get("password")
            group_id = meta.get("group_id")
            if not password or not group_id:
                continue
            await conn.execute(
                "INSERT INTO users (username, password_hash, role, group_id) "
                "VALUES ($1, $2, 'group', $3) "
                "ON CONFLICT (username) DO NOTHING",
                str(username),
                hash_password(str(password)),
                str(group_id),
            )

        # servers 归属：按 SERVER_GROUP_MAP 校正已存在的服务器（未列出的保持现状/归 default）
        for server_id, gid in config.SERVER_GROUP_MAP.items():
            if not gid:
                continue
            await conn.execute(
                "UPDATE servers SET group_id = $2, updated_at = now() WHERE server_id = $1",
                server_id,
                str(gid),
            )
        await conn.execute(
            "UPDATE servers SET group_id = 'default' WHERE group_id IS NULL"
        )
