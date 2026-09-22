# Stage 6-B 实现设计：异常中心历史字段（首次/最近/次数/是否恢复）

> 日期：2026-08-26　阶段：实现设计（待确认后编码）　前置：Stage6-B 调查通过

## 0. 可执行性结论

GPT 方案**可执行**，逐条核对：

| 要求 | 评估 |
|---|---|
| v1 只做 3 类设备异常历史（需换号/风险临界/设备离线） | ✅ events 表已含全部原始数据 |
| server_offline 历史暂不实现，保留实时判断 | ✅ 无阻塞 |
| 30 天窗口，参数化 days | ✅ 接口 query 参数 |
| 不新增独立页面，Alerts.vue 加历史字段 | ✅ 前端改造 |
| 不新增表/schema/agent/业务/规则引擎 | ✅ 中央读侧新增 + 纯函数翻转检测 |

---

## 1. 数据源（复用 events + devices）

- **heartbeat**（每 60s，全量设备快照）→ 提供 `needs_replacement`（需换号）+ `risk_score`（重算 risk_critical）
- **device_status**（每 30s/台）→ 提供 `online_status`（设备离线）
- **devices 当前快照** → 提供「是否恢复」判定

3 类异常维度与数据字段映射：

| 维度 | 异常判定 | 事件来源 |
|---|---|---|
| account_needs_replacement | `needs_replacement == true` | heartbeat.devices[].needs_replacement |
| risk_critical | `derive_risk_status(risk_score, needs_replacement, warn, crit) == 'critical'` | heartbeat.devices[].risk_score + needs_replacement（复用 app/risk.py） |
| device_offline | `online_status == 'offline'` | device_status.online_status |

---

## 2. 后端新增读侧接口

### 2.1 `GET /api/devices/anomaly-history?days=30&server_id=JP-01`

- `days`：时间窗口（默认 30，参数化，后续可调）
- `server_id`：可选，不传则全部服务器

返回（3 个维度平铺在每台设备对象上）：

```json
{
  "history": [
    {
      "server_id": "JP-01",
      "device_id": "cloud-07",
      "account_needs_replacement": {"first_at": "2026-08-26T02:00:00Z", "last_at": "2026-08-26T02:00:00Z", "count": 1, "recovered": false},
      "risk_critical":            {"first_at": "…", "last_at": "…", "count": 1, "recovered": false},
      "device_offline":           {"first_at": "…", "last_at": "…", "count": 2, "recovered": true}
    }
  ]
}
```

- `first_at` / `last_at`：ISO 时间（timestamptz，UTC）；该维度从未异常时为 `null`
- `count`：进入异常态的翻转次数
- `recovered`：**当前**该维度是否已回到正常态（结合 devices 快照）

### 2.2 查询逻辑

1. 查 events（限定窗口 + event_type 过滤）：
```sql
SELECT server_id, event_type, event_ts, payload
FROM events
WHERE server_id = ANY($1)
  AND event_ts >= now() - make_interval(days => $2)
  AND event_type IN ('heartbeat', 'device_status')
ORDER BY server_id, event_ts ASC
```
2. 代码遍历，构建每台设备的**观测序列**：
   - heartbeat → 对每台设备记录 `(event_ts, needs_replacement)` 和 `(event_ts, risk_status 重算值)`
   - device_status → 记录 `(event_ts, online_status)`
3. 对每台设备 × 3 维度，调用纯函数 `detect_anomaly_history()` 算 {first_at, last_at, count}
4. 结合 devices 当前快照填 `recovered`

### 2.3 性能提示

- 30 天 device_status ≈ 每台 30s 一条 → 15 台 × 2×60×24×30 ≈ 130 万条，是数据量大头。
- **优化建议**：device_status 用 SQL 窗口函数 `lag()` 只取「online_status 变化点」（翻转检测只需变化点，无需每条）；heartbeat 的 `devices[]` 展开用 `jsonb_array_elements`，同样只取 needs_replacement 变化点。v1 若嫌复杂可先直扫，加时间窗口兜底，必要时再优化。

---

## 3. 翻转检测纯函数（app/history.py）

沿用 `app/risk.py` / `app/account.py` 的「纯函数、零依赖、可单测」模式：

```python
def detect_anomaly_history(observations, is_anomalous, current_anomalous):
    """observations: 按时间升序的 [(ts, value)]；is_anomalous(value)->bool；
    current_anomalous: 当前快照是否异常。
    返回 {"first_at","last_at","count","recovered"}。
    """
```

语义定义：
- **first_at** = 窗口内第一次观测到异常态的时间（首个 is_anomalous=True 的 ts）
- **last_at** = 最后一次「正常→异常」翻转的时间（若持续异常则 = first_at）
- **count** = 「正常→异常」翻转次数（≥1 当曾异常）
- **recovered** = `not current_anomalous`

> 边界说明：窗口起点若已是异常态，则无法观测到起点前的「首次」，v1 取「窗口内第一次异常观测时间」作为近似 first_at（可接受，30 天窗口足够长）。

---

## 4. 前端展示（Alerts.vue）

1. `api/index.js` 新增 `getAnomalyHistory(days)`。
2. Alerts.vue 拉取 history，构建 `device_id → anomalies` 映射。
3. 当前异常列表（每条 alert 有 `entity=device_id` + `dimension`），新增列：

| 新列 | 取值 |
|---|---|
| 首次发生 | `anomalies[dimension].first_at` |
| 最近发生 | `anomalies[dimension].last_at` |
| 发生次数 | `anomalies[dimension].count` |
| 是否恢复 | `anomalies[dimension].recovered` |

### ⚠️ 「是否恢复」语义（需你拍板，重要）

Alerts.vue **v1 只显示「当前异常」**（`deviceAnomalyOf != null` 才进列表）。因此列表内每条异常的 `recovered` **恒为 false（未恢复）**——「是否恢复」列会恒显示「否」，无区分度。

两种处理，请选其一：

- **A（推荐，最简）**：接口完整返回 4 字段（含 recovered），但 **Alerts.vue 列表只加「首次/最近/次数」3 列**，不展示恒「否」的恢复列；recovered 留接口层为后续扩展。
- **B（让「是否恢复」有意义）**：Alerts.vue 列表**同时显示「当前异常」+「最近已恢复异常」**（recovered=true 的历史异常也列出来，带恢复标记）。这样 4 列都有意义，但列表不再是纯「当前异常」，范围略扩大。

---

## 5. 修改文件范围

| 文件 | 动作 |
|---|---|
| `app/history.py` | **新增**：`detect_anomaly_history` 翻转检测纯函数 |
| `app/query.py` | 新增 `GET /api/devices/anomaly-history` 读侧接口 |
| `tests/test_history.py` | **新增**：翻转检测单测 |
| `web/src/api/index.js` | 新增 `getAnomalyHistory(days)` |
| `web/src/views/Alerts.vue` | 拉历史 + 加历史字段列 |

**不改**：schema.sql / ingest.py / risk.py / account.py / monitor-agent / 业务机 / docker-compose.yml / config.py

---

## 6. 需你拍板 2 点

1. **「是否恢复」列**：选 A（列表只加 3 列，recovered 留接口）还是 B（列表含已恢复异常，4 列都有意义）？
2. 确认 `first_at` 边界口径：窗口起点已异常时，取「窗口内第一次异常观测时间」作为近似首次发生（30 天窗口）——是否接受？
