-- =============================================================================
-- LINE CRM 中央监控 Dashboard — PostgreSQL Schema
-- P1 范围：servers + devices + events（heartbeat + device_status/online）
--
-- 时间约定：
--   - 所有 timestamptz 列存 UTC（写入带 tz 的 datetime）
--   - 展示层与 daily_statistics 按 Asia/Taipei 处理（聚合留 P2）
-- 幂等：CREATE TABLE IF NOT EXISTS，可重复执行。
-- =============================================================================

-- ── 业务服务器 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS servers (
    server_id              TEXT PRIMARY KEY,          -- 例 'JP-01'（agent 从 monitor.yaml 读入注入）
    group_id               TEXT NOT NULL DEFAULT 'default',  -- 归属组（权限隔离，Stage7-E）
    agent_version          TEXT,
    agent_instance_id      TEXT,                      -- 区分 agent 重启
    agent_started_at       TIMESTAMPTZ,
    agent_last_seen_at     TIMESTAMPTZ,               -- agent 最后成功上传中央时间（非业务事件时间）
    last_heartbeat_at      TIMESTAMPTZ,               -- 最后一次 heartbeat 事件时间
    last_heartbeat_payload JSONB,
    pending_count          INTEGER NOT NULL DEFAULT 0,
    cpu_percent            REAL,
    memory_percent         REAL,
    disk_percent           REAL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 设备（三态拆分 + 快照 + latest-wins 字段）──────────────────────────────
CREATE TABLE IF NOT EXISTS devices (
    server_id                 TEXT NOT NULL,
    device_id                 TEXT NOT NULL,

    -- 三态拆分（事件驱动；P1 只维护 online_status）
    online_status             TEXT,                    -- online / offline（NULL = 未上报）
    risk_status               TEXT,                    -- P2
    account_status            TEXT,                    -- P2

    -- 设备稳定快照（heartbeat 最新覆盖；源映射见 README）
    needs_replacement         BOOLEAN NOT NULL DEFAULT false,
    today_success             INTEGER NOT NULL DEFAULT 0,
    today_fail                INTEGER NOT NULL DEFAULT 0,
    risk_score                INTEGER NOT NULL DEFAULT 0,
    last_task_at              TIMESTAMPTZ,
    cooldown_count            INTEGER NOT NULL DEFAULT 0,
    cooldown_until            TIMESTAMPTZ,

    -- latest-wins 排序字段（= 事件 ts）
    status_updated_at         TIMESTAMPTZ,
    -- 展示/审计（不参与排序）
    online_status_changed_at  TIMESTAMPTZ,
    risk_status_changed_at    TIMESTAMPTZ,
    account_status_changed_at TIMESTAMPTZ,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (server_id, device_id)
);

-- ── 事件（幂等：event_id UNIQUE；写入用 ON CONFLICT(event_id) DO NOTHING）──
CREATE TABLE IF NOT EXISTS events (
    event_id     UUID PRIMARY KEY,                     -- UUID4，main.py 或 agent 生成
    server_id    TEXT NOT NULL,
    event_type   TEXT NOT NULL,                        -- heartbeat / device_status / task_result / error_event
    event_ts     TIMESTAMPTZ NOT NULL,                 -- 事件时间（epoch float 秒 → timestamptz UTC）
    payload      JSONB,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 查询索引
CREATE INDEX IF NOT EXISTS idx_events_server_ts ON events (server_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_type_ts   ON events (event_type, event_ts);
CREATE INDEX IF NOT EXISTS idx_devices_server   ON devices (server_id);
CREATE INDEX IF NOT EXISTS idx_devices_replace  ON devices (needs_replacement) WHERE needs_replacement;

-- ── 用户组（Stage7-E 权限底座）───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS groups (
    id          TEXT PRIMARY KEY,               -- 'jp-team'
    name        TEXT NOT NULL,                  -- '日本运营组'
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 用户（Stage7-E 权限底座）───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,                -- pbkdf2_sha256$iters$salt$hash
    role          TEXT NOT NULL DEFAULT 'group',-- 'admin' | 'group'
    group_id      TEXT,                         -- role='group' 必填；admin 为 NULL
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- servers 归属组迁移（老库幂等加列；已存在的 JP-01/JP-02 由 DEFAULT 填 'default'）
ALTER TABLE servers ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT 'default';

-- 按组过滤索引
CREATE INDEX IF NOT EXISTS idx_servers_group ON servers (group_id);

CREATE TABLE IF NOT EXISTS daily_statistics (
    server_id   TEXT    NOT NULL,
    device_id   TEXT    NOT NULL,
    stat_date   DATE    NOT NULL,              -- Asia/Taipei 自然日
    success     INTEGER NOT NULL DEFAULT 0,
    fail        INTEGER NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (server_id, device_id, stat_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_stat_date_server
    ON daily_statistics (stat_date, server_id);
