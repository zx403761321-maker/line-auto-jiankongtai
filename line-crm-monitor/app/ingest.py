"""/api/ingest — 业务机 agent 批量上报事件（幂等 + latest-wins）。"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import config
from .db import get_pool

log = logging.getLogger("ingest")

router = APIRouter()


class IngestEvent(BaseModel):
    event_id: uuid.UUID
    event_type: str
    ts: float  # epoch float 秒（UTC）
    payload: dict = Field(default_factory=dict)


class IngestRequest(BaseModel):
    server_id: str
    agent_version: str | None = None
    agent_instance_id: str | None = None
    agent_started_at: float | None = None
    pending_count: int = 0
    events: list[IngestEvent]


def _dt(ts: float | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


TAIPEI_OFFSET = timedelta(hours=8)          # Asia/Taipei 无 DST


def _taipei_date(ts: float) -> date:
    return (datetime.fromtimestamp(ts, tz=timezone.utc) + TAIPEI_OFFSET).date()


def _stat_date(d: dict, ev) -> date:
    """daily_statistics 落桶日期：优先取 agent 上报的权威 daily_date。

    daily_date 是业务侧 _maybe_reset_daily 用 time.strftime("%Y-%m-%d") 在
    TZ=Asia/Taipei 下写入的台北日历日，直接当日期用，不做时区换算。
    缺失 / 非法（老 agent、fallback 字典）→ 回退心跳到达时间 _taipei_date(ev.ts)。
    """
    dd = d.get("daily_date")
    if isinstance(dd, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd):
        try:
            return date.fromisoformat(dd)
        except ValueError:
            pass
    return _taipei_date(ev.ts)


async def _require_ingest(x_ingest_token: str | None = Header(default=None)) -> None:
    if not config.INGEST_TOKEN:
        raise HTTPException(status_code=503, detail="INGEST_TOKEN not configured")
    if x_ingest_token != config.INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="invalid ingest token")


async def _mark_agent_seen(
    conn: asyncpg.Connection, server_id: str, pending_count: int
) -> None:
    """每次成功上报都刷新 agent_last_seen_at 与 pending_count（与事件去重无关）。

    首次出现该 server 时按 SERVER_GROUP_MAP 归组（仅 INSERT 设一次，后续心跳不覆盖）。
    """
    group_id = config.SERVER_GROUP_MAP.get(server_id, "default")
    await conn.execute(
        """
        INSERT INTO servers (server_id, group_id, agent_last_seen_at, pending_count)
        VALUES ($1, $2, now(), $3)
        ON CONFLICT (server_id) DO UPDATE
            SET agent_last_seen_at = now(),
                pending_count = EXCLUDED.pending_count,
                updated_at = now()
        """,
        server_id,
        group_id,
        pending_count,
    )


async def _apply_heartbeat(
    conn: asyncpg.Connection, server_id: str, ev: IngestEvent, req: IngestRequest
) -> None:
    p = ev.payload
    # servers 全量覆盖（pending_count 已由 _mark_agent_seen 处理）
    await conn.execute(
        """
        INSERT INTO servers (server_id, agent_version, agent_instance_id, agent_started_at,
                             last_heartbeat_at, last_heartbeat_payload,
                             cpu_percent, memory_percent, disk_percent)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (server_id) DO UPDATE SET
            agent_version = EXCLUDED.agent_version,
            agent_instance_id = EXCLUDED.agent_instance_id,
            agent_started_at = EXCLUDED.agent_started_at,
            last_heartbeat_at = EXCLUDED.last_heartbeat_at,
            last_heartbeat_payload = EXCLUDED.last_heartbeat_payload,
            cpu_percent = EXCLUDED.cpu_percent,
            memory_percent = EXCLUDED.memory_percent,
            disk_percent = EXCLUDED.disk_percent,
            updated_at = now()
        """,
        server_id,
        req.agent_version,
        req.agent_instance_id,
        _dt(req.agent_started_at),
        _dt(ev.ts),
        p,
        p.get("cpu_percent"),
        p.get("memory_percent"),
        p.get("disk_percent"),
    )
    # devices 快照（最新覆盖）
    for d in p.get("devices", []):
        if not d.get("device_id"):
            continue
        await conn.execute(
            """
            INSERT INTO devices (server_id, device_id, needs_replacement,
                                 today_success, today_fail, risk_score, last_task_at,
                                 cooldown_count, cooldown_until)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (server_id, device_id) DO UPDATE SET
                needs_replacement = EXCLUDED.needs_replacement,
                today_success = EXCLUDED.today_success,
                today_fail = EXCLUDED.today_fail,
                risk_score = EXCLUDED.risk_score,
                last_task_at = EXCLUDED.last_task_at,
                cooldown_count = EXCLUDED.cooldown_count,
                cooldown_until = EXCLUDED.cooldown_until,
                updated_at = now()
            """,
            server_id,
            d["device_id"],
            d.get("needs_replacement", False),
            d.get("today_success", 0),
            d.get("today_fail", 0),
            d.get("risk_score", 0),
            _dt(d.get("last_task_at")),
            d.get("cooldown_count", 0),
            _dt(d.get("cooldown_until")),
        )
        # ── daily_statistics：仅当 success/fail 均为合法非负整数才落库（防御）──
        s_val = d.get("today_success")
        f_val = d.get("today_fail")
        s_ok = type(s_val) is int and s_val >= 0
        f_ok = type(f_val) is int and f_val >= 0
        if s_ok and f_ok:
            sd = _stat_date(d, ev)
            await conn.execute(
                """
                INSERT INTO daily_statistics (server_id, device_id, stat_date, success, fail)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (server_id, device_id, stat_date) DO UPDATE SET
                    success = GREATEST(daily_statistics.success, EXCLUDED.success),
                    fail    = GREATEST(daily_statistics.fail, EXCLUDED.fail),
                    updated_at = now()
                """,
                server_id, d["device_id"], sd, s_val, f_val,
            )
        else:
            log.warning(
                "daily_statistics 跳过 device=%s（success=%r ok=%s, fail=%r ok=%s）",
                d.get("device_id"), s_val, s_ok, f_val, f_ok,
            )


async def _apply_device_status(
    conn: asyncpg.Connection, server_id: str, ev: IngestEvent
) -> None:
    p = ev.payload
    device_id = p.get("device_id")
    if not device_id:
        return
    online_status = p.get("online_status", "unknown")
    # latest-wins：仅当新事件 >= 当前 status_updated_at 才更新；
    # online_status_changed_at 仅在值真正变化时刷新
    await conn.execute(
        """
        INSERT INTO devices (server_id, device_id, online_status, status_updated_at, online_status_changed_at)
        VALUES ($1,$2,$3,$4,$4)
        ON CONFLICT (server_id, device_id) DO UPDATE SET
            online_status = EXCLUDED.online_status,
            status_updated_at = EXCLUDED.status_updated_at,
            online_status_changed_at = CASE
                WHEN devices.online_status IS DISTINCT FROM EXCLUDED.online_status
                THEN EXCLUDED.status_updated_at
                ELSE devices.online_status_changed_at
            END,
            updated_at = now()
        WHERE devices.status_updated_at IS NULL OR EXCLUDED.status_updated_at >= devices.status_updated_at
        """,
        server_id,
        device_id,
        online_status,
        _dt(ev.ts),
    )


@router.post("/ingest", dependencies=[Depends(_require_ingest)])
async def ingest(req: IngestRequest) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _mark_agent_seen(conn, req.server_id, req.pending_count)
            for ev in req.events:
                inserted = await conn.fetchval(
                    """
                    INSERT INTO events (event_id, server_id, event_type, event_ts, payload)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    ev.event_id,
                    req.server_id,
                    ev.event_type,
                    _dt(ev.ts),
                    ev.payload,
                )
                if inserted is None:
                    continue  # 已入库（重试/重复），跳过副作用
                if ev.event_type == "heartbeat":
                    await _apply_heartbeat(conn, req.server_id, ev, req)
                elif ev.event_type == "device_status":
                    await _apply_device_status(conn, req.server_id, ev)
                # 其他 event_type（task_result/error_event 等 P2）仅入库，不做副作用
    return {"ok": True, "received": len(req.events)}
