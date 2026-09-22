# LINE CRM 中央监控 Dashboard（Central Monitor Server）

多台业务服务器（JP-01 等）的统一观测系统。**只做**收集 / 统计 / 展示 / 判异 / 报警，
**禁止**控制业务、修改业务配置、成为业务 SPOF。

> 部署目标：用户**本地电脑**（Server 模式，非云服务器、非 localhost 单机工具）。

## 架构

```
业务机 main.py ──append_event()──> data/state/monitor_events.jsonl
                                        │ monitor-agent tail
                                        ▼
                          HTTPS /api/ingest（monitor_url 可配置）
                                        ▼
                          本机：PostgreSQL + FastAPI + (Vue P2)
```

- **monitor-agent**：业务机上的独立 sibling 容器，tail JSONL、注入 `server_id`、采集
  主机/设备快照，批量上报中央。
- **中央**：`FastAPI`（0.0.0.0）+ `PostgreSQL`，接收幂等写入 + 查询接口。Vue Dashboard 属 P2。

## 快速部署（本地电脑）

```bash
cp .env.example .env   # 填写 POSTGRES_PASSWORD / INGEST_TOKEN
docker compose up -d --build
# 验证
curl http://localhost:8000/health
```

- API 监听 `0.0.0.0`，端口由 `API_PORT` 控制（默认 8000）。
- 局域网访问 `http://<本机IP>:8000`；Tailscale 由宿主机入网后 `http://<tailscale-ip>:8000`。
- TLS 由反向代理或 Tailscale 终结，P1 代码层只提供 HTTP。

## 鉴权（fail-closed）

| 用途 | 变量 | 说明 |
|---|---|---|
| 写入 `/api/ingest` | `INGEST_TOKEN` | **必填**，未配置时 ingest 返回 503 |
| 读取 `/api/servers` `/api/devices` | `VIEW_TOKEN` | 可选；暴露到局域网/Tailscale 前建议设置 |

agent 请求头：`X-Ingest-Token: <INGEST_TOKEN>`；浏览器读接口：`X-View-Token: <VIEW_TOKEN>`。

## 事件协议（agent ↔ 中央）

`POST /api/ingest`，body：

```json
{
  "server_id": "JP-01",
  "agent_version": "0.1.0",
  "agent_instance_id": "<uuid4，agent 每次启动生成>",
  "agent_started_at": 1750000000.0,
  "pending_count": 3,
  "events": [
    {"event_id": "<uuid4>", "event_type": "heartbeat", "ts": 1750000000.0, "payload": {...}},
    {"event_id": "<uuid4>", "event_type": "device_status", "ts": 1750000000.0, "payload": {...}}
  ]
}
```

所有 `ts` / 时间字段均为 **epoch float 秒（UTC，`time.time()`）**。

### heartbeat payload

```json
{
  "cpu_percent": 12.3,
  "memory_percent": 45.6,
  "disk_percent": 78.9,
  "docker": {"containers": 3, "up": 3},
  "devices": [
    {
      "device_id": "cloud-01",
      "today_success": 5,
      "today_fail": 0,
      "risk_score": 20,
      "last_task_at": 1750000000.0,
      "cooldown_count": 3,
      "cooldown_until": 1750100000.0,
      "needs_replacement": true
    }
  ]
}
```

快照字段数据源（业务机）：

| 字段 | 来源 |
|---|---|
| `today_success` | `bridge.db` `account_status.daily_success` |
| `today_fail` | `bridge.db` `account_status.daily_fail` |
| `risk_score` | `bridge.db` `account_status.risk_score` |
| `last_task_at` | `bridge.db` `account_status.last_task_at` |
| `cooldown_count` | `device_limit_status.json` |
| `cooldown_until` | `device_limit_status.json` |
| `needs_replacement` | `device_limit_status.json` `status=="needs_replacement"`（`cooling_down` ≠ 此） |

### device_status payload（P1 仅 online 维度）

```json
{"device_id": "cloud-01", "online_status": "online"}
```

`online_status` = adb 可达性（`/health` 的 `adb shell echo ok` 结果）。

## 幂等与乱序

- `events.event_id` UNIQUE；写入 `ON CONFLICT(event_id) DO NOTHING`，重复上报跳过副作用。
- `device_status`：`devices.status_updated_at` latest-wins（新事件 ≥ 当前才更新）。
- `heartbeat`：快照最新覆盖（依赖 agent 有序 outbox 保证顺序）。

## 查询接口

| 接口 | 说明 |
|---|---|
| `GET /api/servers` | 服务器列表（含 `online` 判离线，阈值 `STALENESS_SECONDS` 默认 300s） |
| `GET /api/servers/{server_id}` | 单台详情 |
| `GET /api/devices?server_id=&needs_replacement=` | 设备列表（可过滤） |

## 数据口径说明

- `daily_statistics` 用 `GREATEST` 累积（`app/ingest.py`）：heartbeat 每次携带「今日」累计成功/失败，
  每日取峰值即为当日终值，因此**停运设备不会把旧值带进新一天**（按 `_taipei_date(ev.ts)` 归日）。
- 归日边界是 Asia/Taipei 自然日；跨午夜那一次 heartbeat 的 `today_*` 可能归到前一日，
  由 GREATEST 收敛为峰值，不丢数、不重复计。
- 「今日」口径（Overview）用设备快照 `today_success/today_fail`；「昨日/历史」用 `daily_statistics`
  聚合（只统计已过去的日期，今天的累积不完整、不作为今日口径）。

## 目录

```
schema.sql          # PostgreSQL DDL（幂等）
app/
  main.py           # FastAPI 入口（0.0.0.0 + CORS）
  config.py         # 环境变量配置
  db.py             # asyncpg 连接池 + schema 初始化
  ingest.py         # POST /api/ingest（幂等 + latest-wins）
  cleanup.py        # events 过期分批清理（后台任务）
  query.py          # 查询接口
```
