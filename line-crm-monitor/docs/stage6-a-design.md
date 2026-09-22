# Stage 6-A 设计审查：Server 页面增强

> 日期：2026-08-26　阶段：设计审查（未编码）　前置：P2 Stage1-5B 均上线

## 0. GPT 要求评估结论

GPT 给的 3 项指标 + 5 条约束，**逐条核对后全部符合项目现状，无需调整**：

| GPT 要求 | 评估 | 依据 |
|---|---|---|
| 云手机数量 | ✅ 可做 | 前端按 `server_id` 聚合 `/api/devices` 即可 |
| 在线云手机数量 | ✅ 可做 | `online_status == 'online'`，与 Overview 一致 |
| 异常云手机数量 | ✅ 可做 | 复用异常中心判定（见 §3） |
| 优先复用已有 API 数据 | ✅ 满足 | `/api/devices` 已含 server_id/online_status/risk_status/account_status |
| 不新增数据库字段 | ✅ 满足 | 纯前端聚合，零后端 |
| 不修改 monitor-agent | ✅ 满足 | 零改动 |
| 不修改业务机 | ✅ 满足 | 零改动 |
| 异常定义与 Exception Center/risk_status/account_status 一致 | ✅ 满足 | 抽共享判定函数，单一真源（§3） |

---

## 1. 现状与数据源核对

- **Servers.vue 当前**：只用 `getServers()`，每台服务器一行，列 = server_id / online / CPU% / 内存% / 磁盘% / agent 版本 / 最后心跳 / 心跳新鲜度。**无任何设备统计**。
- **`/api/servers`**（`query.py::list_servers`）：只返回服务器自身字段（online/资源/agent），**不含设备数量**。
- **`/api/devices`**（`query.py::list_devices`）：`SELECT * FROM devices` 返回 `server_id` / `device_id` / `online_status` / `risk_status` / `account_status` / `needs_replacement` 等（Stage3/4 已读侧派生 risk/account 两态）。

**结论**：三个指标全部能从 `/api/devices` 按 `server_id` 前端聚合得出，**零后端 / 零 DB / 零 agent / 零业务机改动**。

---

## 2. 三个指标定义（按 server 分组）

对每台服务器 `S`，在其设备子集（`devices` 中 `server_id == S`）上统计：

| 指标 | 定义 | 与现有页面对齐 |
|---|---|---|
| 云手机数量 | 该 server 设备总数 `count` | = Overview「设备总数」的按 server 拆解 |
| 在线云手机数量 | `online_status == 'online'` 的数量 | = Overview「在线设备」同款字段 |
| 异常云手机数量 | 命中异常判定的设备数（去重后，§3） | = 异常中心 device 维度异常数 |

> 「云手机」= 业务术语，「设备」= 中央监控术语，同一实体（devices 表一行 = 一台云手机）。

---

## 3. 异常设备定义（与异常中心对齐 —— 关键）

异常中心（Alerts.vue）对 device 维度的判定是**优先级去重**：

```
account_status == 'needs_replacement'  → account_needs_replacement（最高）
否则 risk_status == 'critical'          → risk_critical
否则 online_status == 'offline'         → device_offline
否则 无异常
```

**「异常云手机数量」必须复用同一判定**，每台设备最多算 1 次异常。

### 关键设计决策：抽共享判定函数（强烈建议）

当前 Alerts.vue 里这段判定是**内联**的。若 Servers.vue 再复制一份，两处逻辑会漂移，直接违反「与异常中心保持一致」这条硬要求。

**建议新增 `web/src/utils/deviceAnomaly.js`**，作为设备异常判定的**单一真源**：

```js
// 设备异常判定（读侧派生，与 risk_status/account_status 一致）
// 返回该设备当前命中的异常 dimension；无异常返回 null
export function deviceAnomalyOf(d) {
  if (d.account_status === 'needs_replacement') return 'account_needs_replacement'
  if (d.risk_status === 'critical') return 'risk_critical'
  if (d.online_status === 'offline') return 'device_offline'
  return null
}
```

- **Servers.vue**：`if (deviceAnomalyOf(d)) abnormal++`
- **Alerts.vue**：把内联 else-if 换成调用 `deviceAnomalyOf(d)`（顺带消除重复）

这样「异常」定义全项目只有一份，未来改判定只动这一处。

> 注意边界：**异常云手机数量不含服务器离线（server_offline）**。服务器在线性已在 Servers 表第一列 online tag 体现，不重复计入设备异常数。

---

## 4. UI 方案

**方案（推荐）：Server 表格每行追加 3 列**，插在 online 列之后、CPU% 之前：

| 列名 | 宽度 | 展示 |
|---|---|---|
| 云手机 | 90 | 数字 `total` |
| 在线 | 90 | 数字 `online` |
| 异常 | 90 | 数字 `abnormal`，>0 时红色/danger tag，=0 时灰色 |

数据流：Servers.vue 增加 `getDevices()`，新增 computed `devicesByServer`（按 server_id 聚合 total/online/abnormal），表格列用 `deviceStats(row.server_id)` 取数。

**备选（不做，仅记录）**：表格上方加全局汇总卡 —— 不采纳，因为需求是「Server 页面」按 server 维度拆解，不是全局总量（全局已在 Overview）。

---

## 5. 文件修改范围（v1）

| 文件 | 动作 |
|---|---|
| `web/src/utils/deviceAnomaly.js` | **新增**：共享设备异常判定函数 |
| `web/src/views/Servers.vue` | 加 getDevices() + devicesByServer computed + 3 列 |
| `web/src/views/Alerts.vue` | 内联判定替换为调用 `deviceAnomalyOf(d)` |

**不改**：schema.sql / ingest.py / query.py / monitor-agent / 业务机 / docker-compose.yml / config.py。

---

## 6. 验证方案

- 纯前端聚合，**不引入前端测试框架**（与 Stage5-A/B 一致），部署后人工验证。
- 验证点：Server 页每行的「云手机」= 该 server 设备总数（JP-01 = 15）；「在线」+「离线」逻辑自洽；「异常」数量 = 该 server 下 account_needs_replacement ∪ risk_critical ∪ device_offline 去重后数量（当前 JP-01 应 = 4，即 cloud-07/10/13/14 需换号）。
- 交叉验证：与异常中心 /alerts 的 device 维度条数、Devices 页三态分布一致。

---

## 7. 红线确认

- ✅ 不新增数据库字段（纯前端聚合）
- ✅ 不修改 monitor-agent / 业务机
- ✅ 不新增后端接口
- ✅ 异常定义与 Exception Center 单一真源

---

## 8. 需拍板的点

1. **是否采纳「抽共享判定函数」方案 B**（新增 utils/deviceAnomaly.js + Alerts.vue 同步改用）？还是方案 A（Servers.vue 内联复制判定、不改 Alerts.vue，改动最小但有漂移风险）？—— 我强烈建议 B，因为它直接兑现「保持一致」的硬要求。
2. **异常列展示**：数字 >0 用 danger 高亮是否 OK？（无异常时灰字 0）
