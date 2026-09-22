"""/api 查询接口（读侧，可选 VIEW_TOKEN 鉴权）。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from collections import defaultdict

from . import config
from .db import get_pool
from .risk import derive_risk_status
from .account import derive_account_status
from .history import detect_anomaly_history

router = APIRouter()


async def _current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """解析当前访问身份，返回 {username, role, group_id}。

    优先级：
      1. session 登录用户（admin 全量 / group 按 group_id）
      2. Bearer VIEW_TOKEN（系统只读凭证，全量，不绑定 admin 用户）
      3. 两者皆无：PUBLIC_MODE 下 401；本地/Tailscale 开放（全量，兼容旧脚本）
    """
    sess = request.session.get("user")
    if sess:
        return sess
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if config.VIEW_TOKEN:
        if token == config.VIEW_TOKEN:
            return {"username": "__token__", "role": "admin", "group_id": None}
    else:
        if config.PUBLIC_MODE:
            raise HTTPException(status_code=401, detail="authentication required")
        return {"username": "__open__", "role": "admin", "group_id": None}
    raise HTTPException(status_code=401, detail="invalid credentials")


@router.get("/servers")
async def list_servers(user: dict = Depends(_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user["role"] == "admin":
            rows = await conn.fetch(
                """
                SELECT server_id, agent_version, agent_instance_id, agent_started_at,
                       agent_last_seen_at, last_heartbeat_at, pending_count,
                       cpu_percent, memory_percent, disk_percent,
                       CASE WHEN agent_last_seen_at IS NULL THEN NULL
                            ELSE EXTRACT(EPOCH FROM (now() - agent_last_seen_at)) END AS seconds_since_seen
                FROM servers
                ORDER BY server_id
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT server_id, agent_version, agent_instance_id, agent_started_at,
                       agent_last_seen_at, last_heartbeat_at, pending_count,
                       cpu_percent, memory_percent, disk_percent,
                       CASE WHEN agent_last_seen_at IS NULL THEN NULL
                            ELSE EXTRACT(EPOCH FROM (now() - agent_last_seen_at)) END AS seconds_since_seen
                FROM servers
                WHERE group_id = $1
                ORDER BY server_id
                """,
                user["group_id"],
            )
    out = []
    for r in rows:
        d = dict(r)
        d["online"] = (
            d["seconds_since_seen"] is not None
            and d["seconds_since_seen"] <= config.STALENESS_SECONDS
        )
        d["server_ip"] = config.SERVER_IP_MAP.get(d["server_id"], "")
        out.append(d)
    return {"servers": out}


@router.get("/servers/{server_id}")
async def get_server(server_id: str, user: dict = Depends(_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM servers WHERE server_id = $1", server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="server not found")
    d = dict(row)
    # group 用户越权访问他人 server → 404（与「不存在」同响应，防枚举）
    if user["role"] != "admin" and d.get("group_id") != user["group_id"]:
        raise HTTPException(status_code=404, detail="server not found")
    return d


@router.get("/devices")
async def list_devices(
    server_id: str | None = Query(default=None),
    needs_replacement: bool | None = Query(default=None),
    user: dict = Depends(_current_user),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        sql = "SELECT * FROM devices WHERE 1=1"
        args: list = []

        if user["role"] != "admin":
            srows = await conn.fetch(
                "SELECT server_id FROM servers WHERE group_id = $1", user["group_id"]
            )
            allowed = [r["server_id"] for r in srows]
            if server_id is not None:
                # 显式指定 server：必须属于本组，否则 404（防越权/枚举）
                if server_id not in allowed:
                    raise HTTPException(status_code=404, detail="server not found")
            else:
                # 未指定：仅返回本组
                args.append(allowed)
                sql += f" AND server_id = ANY(${len(args)}::text[])"

        if server_id is not None:
            args.append(server_id)
            sql += f" AND server_id = ${len(args)}"
        if needs_replacement is not None:
            args.append(needs_replacement)
            sql += f" AND needs_replacement = ${len(args)}"
        sql += " ORDER BY server_id, device_id"
        rows = await conn.fetch(sql, *args)
    out = []
    for r in rows:
        d = dict(r)
        d["risk_status"], d["risk_reason"] = derive_risk_status(
            d["risk_score"],
            d["needs_replacement"],
            config.RISK_WARNING_THRESHOLD,
            config.RISK_CRITICAL_THRESHOLD,
        )
        d["account_status"], d["account_reason"] = derive_account_status(
            d["needs_replacement"],
            d["cooldown_until"],
        )
        out.append(d)
    return {"devices": out}


@router.get("/devices/anomaly-history")
async def anomaly_history(
    days: int = Query(default=30, ge=1, le=365),
    server_id: str | None = Query(default=None),
    user: dict = Depends(_current_user),
):
    """设备级异常历史（读侧，从 events 表重建；v1 仅 3 类设备异常，不含 server_offline）。

    first_at 语义：查询时间窗口（days 参数，最近 N 天滚动窗口）内首次观测到
    异常的时间，不代表设备生命周期首次异常。

    性能：device_offline 由 SQL 窗口函数聚合（device_status 约 152 万行，不拉回
    Python）；replacement / risk 来自 heartbeat（约 4.9 万行，Python 照旧派生）。
    权限：allowed server_ids 先算好，events 与当前快照两处查询都在 SQL 侧过滤。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user["role"] != "admin":
            srows = await conn.fetch(
                "SELECT server_id FROM servers WHERE group_id = $1 ORDER BY server_id",
                user["group_id"],
            )
            allowed = [r["server_id"] for r in srows]
            if server_id:
                if server_id not in allowed:
                    raise HTTPException(status_code=404, detail="server not found")
                server_ids = [server_id]
            else:
                server_ids = allowed
        else:
            if server_id:
                server_ids = [server_id]
            else:
                srows = await conn.fetch("SELECT server_id FROM servers ORDER BY server_id")
                server_ids = [r["server_id"] for r in srows]
        if not server_ids:
            return {"history": []}

        # replacement / risk：只取 heartbeat（约 4.9 万行），命中 idx_events_server_ts
        rows = await conn.fetch(
            """
            SELECT server_id, event_ts, payload
            FROM events
            WHERE server_id = ANY($1::text[])
              AND event_ts >= now() - make_interval(days => $2)
              AND event_type = 'heartbeat'
            ORDER BY server_id, event_ts ASC
            """,
            server_ids,
            days,
        )

        # device_offline：device_status 约 152 万行，窗口函数在 SQL 侧聚合为每设备一行
        offline_rows = await conn.fetch(
            """
            WITH ordered AS (
                SELECT server_id,
                       payload->>'device_id' AS device_id,
                       event_ts,
                       payload->>'online_status' AS st,
                       lag(payload->>'online_status') OVER (
                           PARTITION BY server_id, payload->>'device_id'
                           ORDER BY event_ts ASC
                       ) AS prev_st
                FROM events
                WHERE server_id = ANY($1::text[])
                  AND event_ts >= now() - make_interval(days => $2)
                  AND event_type = 'device_status'
            )
            SELECT server_id, device_id,
                   min(event_ts) FILTER (WHERE st = 'offline') AS first_at,
                   count(*) FILTER (WHERE st = 'offline' AND prev_st IS DISTINCT FROM 'offline') AS flip_count,
                   max(event_ts) FILTER (WHERE st = 'offline' AND prev_st IS DISTINCT FROM 'offline') AS last_at
            FROM ordered
            GROUP BY server_id, device_id
            """,
            server_ids,
            days,
        )

        # 当前 devices 快照（recovered 判定；同样按 allowed server_ids 过滤，防越权）
        dev_rows = await conn.fetch(
            "SELECT server_id, device_id, online_status, risk_score, needs_replacement "
            "FROM devices WHERE server_id = ANY($1::text[])",
            server_ids,
        )

    # 构建每台设备的观测序列（heartbeat 时间已按 event_ts ASC 排好）
    obs = defaultdict(lambda: {"replacement": [], "risk": []})
    for r in rows:
        ts = r["event_ts"]
        p = r["payload"] or {}
        for d in p.get("devices", []):
            did = d.get("device_id")
            if not did:
                continue
            key = (r["server_id"], did)
            nr = bool(d.get("needs_replacement", False))
            risk_status, _ = derive_risk_status(
                d.get("risk_score", 0) or 0,
                nr,
                config.RISK_WARNING_THRESHOLD,
                config.RISK_CRITICAL_THRESHOLD,
            )
            obs[key]["replacement"].append((ts, nr))
            obs[key]["risk"].append((ts, risk_status))

    # 当前快照 → 各维度 current_anomalous
    current = {}
    for r in dev_rows:
        nr = bool(r["needs_replacement"])
        risk_status, _ = derive_risk_status(
            r["risk_score"] or 0,
            nr,
            config.RISK_WARNING_THRESHOLD,
            config.RISK_CRITICAL_THRESHOLD,
        )
        current[(r["server_id"], r["device_id"])] = {
            "replacement": nr,
            "risk": risk_status == "critical",
            "offline": r["online_status"] == "offline",
        }

    # device_offline SQL 聚合结果 → 与 detect_anomaly_history 同语义
    offline_hist = {}
    for r in offline_rows:
        offline_hist[(r["server_id"], r["device_id"])] = {
            "first_at": r["first_at"],
            "last_at": r["last_at"],
            "count": r["flip_count"],
        }

    history = []
    for key in sorted(set(obs.keys()) | set(offline_hist.keys()) | set(current.keys())):
        sid, did = key
        o = obs.get(key) or {"replacement": [], "risk": []}
        c = current.get(key) or {"replacement": False, "risk": False, "offline": False}
        off = offline_hist.get(key)
        history.append(
            {
                "server_id": sid,
                "device_id": did,
                "account_needs_replacement": detect_anomaly_history(
                    o["replacement"], lambda v: v, c["replacement"]
                ),
                "risk_critical": detect_anomaly_history(
                    o["risk"], lambda v: v == "critical", c["risk"]
                ),
                "device_offline": {
                    "first_at": off["first_at"] if off else None,
                    "last_at": off["last_at"] if off else None,
                    "count": off["count"] if off else 0,
                    "recovered": (off["count"] if off else 0) > 0 and not c["offline"],
                },
            }
        )
    return {"history": history}


TAIPEI_OFFSET = timedelta(hours=8)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _taipei_yesterday():
    return (datetime.now(timezone.utc) + TAIPEI_OFFSET - timedelta(days=1)).date()


@router.get("/daily")
async def daily_stats(
    date: str | None = Query(default=None),
    user: dict = Depends(_current_user),
):
    """昨日（或指定日期）任务聚合：先按用户权限取 allowed server_ids，再聚合。

    只统计过去日期；GREATEST 累积中的「今天」结果不完整，不作为今日口径。
    """
    if date is None:
        target = _taipei_yesterday()
    else:
        if not _DATE_RE.match(date):
            raise HTTPException(status_code=400, detail="date 需为 YYYY-MM-DD")
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="非法日期")

    pool = await get_pool()
    async with pool.acquire() as conn:
        if user["role"] == "admin":
            srows = await conn.fetch("SELECT server_id FROM servers")
        else:
            srows = await conn.fetch(
                "SELECT server_id FROM servers WHERE group_id = $1", user["group_id"]
            )
        allowed = [r["server_id"] for r in srows]
        if not allowed:
            return {"date": target.isoformat(), "success": 0, "fail": 0, "failed_devices": 0}

        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(success), 0)              AS success,
                   COALESCE(SUM(fail), 0)                 AS fail,
                   COUNT(*) FILTER (WHERE fail > 0)       AS failed_devices
            FROM daily_statistics
            WHERE stat_date = $1 AND server_id = ANY($2::text[])
            """,
            target,
            allowed,
        )

    return {
        "date": target.isoformat(),
        "success": row["success"],
        "fail": row["fail"],
        "failed_devices": row["failed_devices"],
    }


@router.get("/stats/trend")
async def stats_trend(
    window: str = Query(default="week", pattern="^(week|month)$"),
    month: str | None = Query(default=None),
    user: dict = Depends(_current_user),
):
    """周/月累计趋势：按 Asia/Taipei 自然周/自然月聚合 daily_statistics。

    - week  = 本周一~周日（今天之后的点补 0，供 7 格柱状）
    - month = 本月 1 号~今天；month=YYYY-MM 时查询指定历史月（1 号~月末）
    group 用户仅统计本组服务器，与 /api/daily 一致。
    """
    today = (datetime.now(timezone.utc) + TAIPEI_OFFSET).date()
    if window == "week":
        start = today - timedelta(days=today.weekday())   # 周一
        end = start + timedelta(days=6)                    # 周日
    elif month:
        if not _MONTH_RE.match(month):
            raise HTTPException(status_code=400, detail="month 需为 YYYY-MM")
        try:
            y = int(month[:4])
            m = int(month[5:7])
            start = date(y, m, 1)
            end = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="month 非法")
        if start > today:
            raise HTTPException(status_code=400, detail="不能查询未来月份")
    else:  # month（本月）
        start = today.replace(day=1)                       # 1 号
        end = today                                        # 今天

    pool = await get_pool()
    async with pool.acquire() as conn:
        if user["role"] == "admin":
            srows = await conn.fetch("SELECT server_id FROM servers")
        else:
            srows = await conn.fetch(
                "SELECT server_id FROM servers WHERE group_id = $1", user["group_id"]
            )
        allowed = [r["server_id"] for r in srows]
        if not allowed:
            return {
                "window": window,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "points": [],
                "total_success": 0,
                "total_fail": 0,
            }

        rows = await conn.fetch(
            """
            SELECT stat_date, COALESCE(SUM(success), 0) AS success,
                   COALESCE(SUM(fail), 0) AS fail
            FROM daily_statistics
            WHERE stat_date BETWEEN $1 AND $2 AND server_id = ANY($3::text[])
            GROUP BY stat_date
            ORDER BY stat_date
            """,
            start,
            end,
            allowed,
        )

    by_date = {r["stat_date"]: r for r in rows}
    total_days = (end - start).days + 1
    points = []
    total_success = 0
    total_fail = 0
    for i in range(total_days):
        d = start + timedelta(days=i)
        r = by_date.get(d)
        success = int(r["success"]) if r else 0
        fail = int(r["fail"]) if r else 0
        points.append({"date": d.isoformat(), "success": success, "fail": fail})
        total_success += success
        total_fail += fail

    return {
        "window": window,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "points": points,
        "total_success": total_success,
        "total_fail": total_fail,
    }
