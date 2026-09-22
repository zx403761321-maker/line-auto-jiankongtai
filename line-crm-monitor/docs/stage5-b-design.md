# Stage 5-B 设计审查：Dashboard 内异常中心

> 日期：2026-08-26　阶段：设计审查（未编码）　前置：P2 Stage1-4 + Stage5-A 均上线

## 0. 结论

认可 GPT 方向：**不做外部通知，只在 Dashboard 内做「异常中心」**（当前异常 + 异常历史 + 恢复状态）。

但结合项目现状，有 **3 个关键调整**，调整后方案比 GPT 原方案更轻：

1. **alerts 数据模型 = 读侧派生，不新建表**（新建表破「不改 schema.sql」红线，且要写库逻辑）。
2. **5 个告警来源的数据已全部在现有 API 返回里，前端聚合即可，零后端新增**；且前 2 个来源（heartbeat timeout / agent offline）冗余，建议合并为 1 个 → 实际 **4 个来源**。
3. **「异常历史 / 恢复」需要历史数据，当前架构只有 latest 快照 + events 事件流**，建议分 v1（当前异常，零风险）和 v2（历史恢复，从 events 读侧重建）。

---

## 1. 告警来源梳理（5 → 4）

| GPT 来源 | 判定字段 | 现有数据位置 | 建议 |
|---|---|---|---|
| server heartbeat timeout | last_heartbeat_at 超时 | servers 表 | **合并**为「服务器离线」 |
| agent offline | agent_last_seen_at 超时 | servers（`list_servers` 已算 `online`） | 同上 |
| device offline | online_status = offline | devices（`list_devices` 已返回） | 保留 |
| risk_status critical | risk_status = critical | devices（Stage3 读侧派生） | 保留 |
| account_status needs_replacement | account_status = needs_replacement | devices（Stage4 读侧派生） | 保留 |

**合并理由**：`list_servers` 已经用 `agent_last_seen_at` + `STALENESS_SECONDS`(300s) 判了 `online`，「heartbeat timeout」与「agent offline」本质是同一件事（服务器连接中断），不必拆成两个来源。合并后：

> 最终 4 来源：**服务器离线 / 设备离线 / 风险 critical / 需换号**

**关键结论**：这 4 个来源的数据**全部已在现有 `/api/servers` 和 `/api/devices` 返回里**，无需改 ingest / agent / 业务机，也无需后端新增任何字段。**前端聚合即可。**

---

## 2. alerts 数据模型（读侧派生，不落库）

alerts 不是新表，是**前端从现有 API 聚合出来的数据结构**：

```
alert = {
  entity:   "JP-01"        # 服务器 server_id 或设备 device_id
  kind:     "server"|"device"
  dimension:"server_offline"|"device_offline"|"risk_critical"|"needs_replacement"
  severity: "critical"|"warning"
  reason:   ...            # 复用 risk_reason / account_reason / offline
}
```

不落库、不进 schema —— 与 Stage3/4 的 risk_status/account_status 读侧派生同一哲学。

---

## 3. 去重优先级

一台设备可能同时命中多个维度（如：需换号 + risk critical + 设备离线）。去重规则（取最高优先级的单一维度）：

```
1. account needs_replacement      ← 最高（换号是终局态）
2. risk critical                  （仅当非 needs_replacement）
3. device offline
```

- **needs_replacement 优先于 risk critical**（GPT 已要求）：因为 Stage3 的 critical 规则包含 `needs_replacement==true`，换号设备必然也是 critical，报一次即可。
- **device offline 与上述两个可并存**：一台设备既「需换号」又「离线」，v1 建议合并展示为一条（优先级最高的 dimension + reason 里附注 offline），避免重复行。

---

## 4. 当前异常（v1，建议本轮做）

**实现**：纯前端。新增异常聚合逻辑，从 `getServers()` + `getDevices()` 派生 alerts 列表。

**展示形态**（二选一，需拍板）：
- **A. Overview 顶部「异常横幅」**：异常数量 + 前 N 条摘要，点开跳详情。改动最小，一进首页即见。
- **B. 新增「异常中心」页 `/alerts`**：完整异常列表（服务器段 + 设备段，按 severity 排序）。信息更全，需加路由 + 导航项。

**建议**：A + B 都做（横幅概览 + 独立页详情），但 v1 至少做 A（满足「打开网页就看到异常」）。

---

## 5. 异常历史 / 恢复（v2，建议单独设计）

**约束事实**：当前 devices/servers 表是 latest-wins 快照，无历史；devices 表的 `*_status_changed_at` 三列预留但从未写入（读侧派生不落库）。

**可行路径**：P1 的 `events` 表**已经持久化了全部事件流**（heartbeat 的 payload 含整批设备快照，device_status 含 online 维度）。v2 可**读侧从 events 表重建**「某设备何时进入/退出异常」，不改 schema、不改 ingest。

**但复杂度高**：要按时间窗口解析 JSONB payload、合并 heartbeat（风险/换号）与 device_status（在线）两类事件。因此建议：
- v1 只做「当前异常」（本轮）。
- v2 的「历史/恢复」另开设计审查（读侧 events 聚合 + 可能加一个只读 query 接口）。

---

## 6. 文件修改范围（v1）

| 文件 | 动作 |
|---|---|
| web/src/views/Overview.vue（或新 Alerts.vue） | 加异常聚合 + 展示 |
| web/src/router/index.js + 导航 | 若选 B 需加 /alerts 路由 |

**不改**：schema.sql / ingest.py / monitor-agent / 业务机 / query.py（v1 不需要）。

---

## 7. 红线确认

- ✅ 不增加任何外部通知通道
- ✅ 不改 schema.sql / ingest.py / monitor-agent / 业务机
- ✅ alerts 读侧派生，不落库

---

## 8. 需要你拍板的点

1. **展示形态**：Overview 顶部横幅（A）？还是独立「异常中心」页（B）？还是 A+B？
2. **范围**：本轮只做 v1「当前异常」（我的建议），「历史/恢复」留 v2 单独设计 —— 是否同意？
3. **来源合并**：把「server heartbeat timeout」和「agent offline」合并为「服务器离线」（4 来源）—— 是否同意？
