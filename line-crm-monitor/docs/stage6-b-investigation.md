# Stage 6-B 调查：异常中心历史增强（首次/最近/次数/是否恢复）

> 日期：2026-08-26　阶段：设计调查（只读，不编码）　前置：Stage6-A 已上线

## 0. 结论（TL;DR）

- **数据已足够**：`events` 表结构 + 现有两类事件流，已覆盖「首次发生时间 / 最近发生时间 / 发生次数 / 是否恢复」全部 4 个目标字段所需的原始数据。
- **缺的不是数据，是「读侧历史聚合查询」**：当前 query.py 只有 latest-wins 快照接口（list_servers/list_devices），前端 Alerts.vue 只依赖当前快照，从未有「按时间扫描事件流」的读侧能力。
- **无需改业务、无需改 agent、无需改 schema**：3 个设备维度异常直接可从事件流翻转检测重建；服务器离线从事件流时间间隙间接推导。
- **GPT 意见评估**：「不新增复杂异常系统」「不引入规则引擎」——**合理，可照做**（详见 §5）。

---

## 1. events 表结构（schema.sql）

```sql
CREATE TABLE IF NOT EXISTS events (
    event_id     UUID PRIMARY KEY,
    server_id    TEXT NOT NULL,
    event_type   TEXT NOT NULL,          -- heartbeat / device_status / task_result / error_event
    event_ts     TIMESTAMPTZ NOT NULL,   -- 事件产生时间（epoch 秒 → UTC）
    payload      JSONB,                  -- 事件内容
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()  -- 中央入库时间
);
CREATE INDEX idx_events_server_ts ON events (server_id, event_ts DESC);
```

- 有 `(server_id, event_ts DESC)` 索引，天然支持「按服务器 + 时间倒序扫描事件流」。
- `payload` 是 JSONB，事件内容完整落库，未丢弃任何字段。

---

## 2. events 当前实际内容（代码确认，只有 2 类事件）

事件产生者共两处，**事件内容由代码确定性决定**（非运行时抽样）：

### 2.1 heartbeat —— monitor-agent 每 60s 产生（`agent.py::_push_heartbeat`）

```json
{
  "event_id": "…uuid4…",
  "event_type": "heartbeat",
  "ts": 1724668800.123,
  "payload": {
    "cpu_percent": 23.5,
    "memory_percent": 61.2,
    "disk_percent": 45.0,
    "docker": {"containers": 3, "up": 2},
    "devices": [
      {"device_id": "cloud-01", "today_success": 120, "today_fail": 3,
       "risk_score": 50, "last_task_at": 1724668500.0,
       "cooldown_count": 0, "cooldown_until": null, "needs_replacement": false},
      {"device_id": "cloud-07", "…": "…", "needs_replacement": true}
    ]
  }
}
```

**关键**：`devices[]` 是**全量设备快照**（每台设备的 needs_replacement / risk_score / cooldown_count / cooldown_until / today_success / today_fail / last_task_at）。每条 heartbeat 都带全量，因此构成**每台设备快照的时间序列**。

### 2.2 device_status —— 业务 main.py `/health` 每 30s/台 产生（`main.py:221`）

```json
{
  "event_id": "…uuid4…",
  "event_type": "device_status",
  "ts": 1724668800.456,
  "payload": {"device_id": "cloud-01", "online_status": "online"}
}
```

**关键**：`online_status` 每 30s 一条 per 设备，构成**设备在线状态的时间序列**。

### 2.3 task_result / error_event

schema 注释预留了这两种 event_type，但**当前无产生者**（`grep append_event` 仅 device_status 一处；agent 仅产生 heartbeat）。events 表实际只会有前两类。

---

## 3. 四个目标字段 × 四个异常来源 —— 可实现性矩阵

| 异常来源 | 首次发生 | 最近发生 | 发生次数 | 是否恢复 | 数据源与方式 |
|---|---|---|---|---|---|
| account_needs_replacement | ✅ | ✅ | ✅ | ✅ | heartbeat.devices[].needs_replacement 的 false→true 翻转 |
| risk_critical | ✅（需重算） | ✅（需重算） | ✅（需重算） | ✅（需重算） | heartbeat 的 risk_score+needs_replacement → derive_risk_status 重算 |
| device_offline | ✅ | ✅ | ✅ | ✅ | device_status.online_status 的 online→offline 翻转 |
| server_offline | ⚠️ 间接 | ⚠️ 间接 | ⚠️ 间接 | ⚠️ 间接 | 无直接事件；从该 server 事件流 ingested_at 间隙 ≥ STALENESS_SECONDS(300s) 推导 |

### 字段语义（重要，需与产品确认）

- **首次发生时间**：该异常维度「首次进入异常态」的事件时间（`event_ts`）。
- **最近发生时间**：最近一次「进入异常态」的事件时间。
- **发生次数**：进入异常态的「翻转次数」（如 needs_replacement false→true 次数）。
- **是否已恢复**：当前快照该异常是否已消失（回到正常态）。需结合 events 历史 + 当前 devices/servers 快照共同判断。

---

## 4. 数据缺口（缺的是「查询」，不是「字段」）

### A. 当前已有能力

1. `events` 表完整持久化了全部事件流，`event_ts` + `payload(JSONB)` + `(server_id, event_ts DESC)` 索引，**原始数据齐全**。
2. 设备维度 3 个异常（需换号 / 风险临界 / 设备离线）的历史，**可直接从事件流翻转检测重建**，无需任何新字段。
3. 「是否恢复」结合当前快照（devices.servers 表已存在）即可判定。

### B. 数据缺口

| 缺口 | 原因 |
|---|---|
| 后端无「历史状态翻转」聚合接口 | query.py 只有 latest-wins 快照（list_servers/list_devices），P1/P2 从未有历史聚合需求 |
| 前端无历史数据来源 | Alerts.vue 只依赖 getServers()+getDevices() 当前快照 |
| risk_status 历史需重算 | risk_status 是读侧派生，events 只存 risk_score+needs_replacement；重算需用**当前阈值**（阈值无历史版本，历史重算精度有此限制，但 v1 可接受） |
| server_offline 无直接事件 | 服务器在线性 = agent_last_seen_at 最新值，历史被覆盖；只能从事件流 ingested_at 间隙推导 |

**缺口本质**：不是「数据缺失」，而是「读侧从未提供历史聚合」。实现历史需新增中央读侧查询能力（扫描 events 表）。

---

## 5. 最小改动方案（不编码，仅方案）

### 原则确认

- **不改业务系统**：events 已有全部设备维度数据，无需业务追加事件。
- **不改 monitor-agent**：heartbeat 已含全量设备快照，无需 agent 加字段。
- **不改 schema**：events 表字段已够。
- **不新增规则引擎**：异常判定就是 deviceAnomalyOf 三条规则，历史重建只需「状态翻转检测」（纯 SQL 扫描 / 代码循环），无需规则引擎。

### 方案（中央读侧新增，v1）

1. **新增只读接口**（query.py 内），按 `server_id` + 时间窗口扫描 events 表：
   - 对设备：分别扫 heartbeat（算 needs_replacement / risk_status 翻转）与 device_status（算 online 翻转），产出每台设备的「异常历史摘要」{首次, 最近, 次数, 当前是否异常}。
   - 对服务器：扫该 server 事件流的 `ingested_at` 序列，找 ≥300s 间隙 → 离线区间。
2. **前端 Alerts.vue 增加历史展示**（或独立明细），调用上述接口。

### 需要拍板的复杂度权衡

- 历史聚合是**后端读侧改动 + 前端改动**，不再是 Stage6-A 的「纯前端」。
- 需**限定时间窗口**（如最近 7/30 天）避免全表扫描 JSONB；建议 v1 只做「最近 N 天」，并考虑在 events 表加 `event_type` 过滤（已有索引可加速按 server+ts 扫）。
- server_offline 的「离线区间」判定规则需单独定义清楚（间隙阈值、边界归属），是 4 个来源里唯一需要额外设计的。

### GPT 意见评估

- 「不新增复杂异常系统」—— ✅ **合理**。events 表已够，无需新表/新状态机。
- 「不引入规则引擎」—— ✅ **合理**。翻转检测是确定性逻辑，规则引擎是过度设计。

---

## 6. 结论与建议

- **Stage6-B 可做，且数据层面零阻塞**：4 个目标字段的原始数据 events 表已具备，无需改业务/agent/schema。
- **代价**：需要新增中央读侧「历史聚合」查询 + 前端展示，复杂度高于 Stage6-A（从纯前端 → 后端读侧扫描事件流）。
- **建议 v1 范围**：先做 3 个设备维度异常（需换号 / 风险临界 / 设备离线）的历史，server_offline 的间隙推导作为 v2 或独立设计（它是唯一需额外定义规则的来源）。

是否进入 Stage6-B 编码，请拍板：
1. 范围确认：v1 只做设备维度 3 异常历史，server_offline 延后？
2. 时间窗口：最近 7 天 / 30 天？
3. 展示形态：Alerts.vue 内嵌「历史」列 / 独立明细页？
