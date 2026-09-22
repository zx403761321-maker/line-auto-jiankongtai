# Stage 4 Phase 1 设计审查文档：account_status（账号生命周期展示状态）

> 日期：2026-08-26　阶段：设计审查（未编码）　前置：Phase 0 调查（docs/stage4-phase0-investigation.md）

## 0. 结论先行

采纳 GPT 全部方向。核心决策：

- **account_status 是中央展示派生态**，与业务机 `bridge.db.account_status.status` 完全解耦。
- 唯一数据源 = `device_limit_status.json`（经 heartbeat 快照已采集的 `needs_replacement / cooldown_until`）。
- v1 三态：`active / cooling_down / needs_replacement`，读侧派生，**零 agent / schema / ingest 改动**。
- 新增 `account_reason`，对称 Stage 3 的 `risk_reason`。
- cooling_down 判定用 `cooldown_until` 时间比较（**不用** `cooldown_count`）。

---

## 1. account_status 字段语义

**中央定义**：account_status =「账号生命周期展示状态」，回答"这个账号当前在生命周期哪个阶段"，用于 Dashboard 展示 + 未来 Stage 6 告警。

**它 ≠ bridge.db.account_status.status**。后者是业务机内部、被 `/health` 每 30s 冲成 online/offline 的瞬时可达性字段（Phase 0 已实锤，不可信）。

**数据源（唯一）**：`device_limit_status.json`（template.sh 写，不受 /health 污染），经 monitor-agent `collect_snapshot` → heartbeat 快照 → 中央 devices 表两列：

| 中央列 | 类型 | 来源 |
|---|---|---|
| needs_replacement | BOOLEAN | `status == "needs_replacement"` |
| cooldown_until | TIMESTAMPTZ | `cooldown_until`（`%Y-%m-%d` 日期 → 当天 00:00 台北时间 → UTC） |

**派生态字段**（读侧派生，不落库）：
- `account_status` (TEXT) ∈ active / cooling_down / needs_replacement
- `account_reason` (TEXT) ∈ needs_replacement / cooldown / NULL

---

## 2. 状态枚举

| account_status | 含义 | 数据判据 |
|---|---|---|
| needs_replacement | 需换号（累计 3 次触顶） | needs_replacement == true |
| cooling_down | 冷却中（第 1~2 次触顶，且冷却期内） | 非换号 且 cooldown_until 在未来 |
| active | 正常可执行 | 其余 |

**account_reason 枚举**：

| account_reason | 触发 |
|---|---|
| needs_replacement | account_status = needs_replacement |
| cooldown | account_status = cooling_down |
| NULL | account_status = active |

---

## 3. 推导优先级

```
1. needs_replacement == true                            → ("needs_replacement", "needs_replacement")
2. cooldown_until is not None AND cooldown_until > now  → ("cooling_down", "cooldown")
3. 其余                                               → ("active", None)
```

要点：

- **needs_replacement 优先级最高**：换号设备即使 cooldown_until 仍在未来，也判 needs_replacement。
- **cooling_down 用严格大于** `cooldown_until > now()`；等于 / 过去 = 已到期 = active。
- **cooldown_count 不参与当前状态判断**（历史累计次数，保留展示/统计）。
- **精度说明**：cooldown_until 只到天（device_limit_status.json 存 `%Y-%m-%d`，collect 解析为当天 00:00 台北时间），所以 cooling_down 到期发生在"截止日当天 00:00"，与业务侧 template.sh `check_cooldown` 语义一致。
- **语义取舍**：中央派生的 active 反映"当前是否还在冷却期"（时间语义），可能与 device_limit_status.json 里残留的 `status="cooling_down"` 字段（历史语义，只在下次触顶才更新）短暂不一致 —— 这是**正确行为**，冷却期满即恢复 active。

---

## 4. API 变化

- `/api/devices` 每个 device 对象新增 `account_status`、`account_reason` 两字段（读侧派生，同 risk_status / risk_reason）。
- 无新 endpoint；无 schema 变更（devices.account_status 列已存在，保持 NULL，不落库）。
- 无新配置 / env（account_status 派生不需要阈值，不同于 risk 的 40/90）。

---

## 5. Dashboard 展示

- **Devices.vue** 列表新增 `account_status` 列（risk_status 列旁），el-tag 类型映射：
  - needs_replacement → `danger`
  - cooling_down → `warning`
  - active → `success`
  - `account_reason` 作 title 提示（同 risk_reason 手法）。
- **Overview.vue 暂不动**（保持 Stage 3 三组）。可选扩展：第 4 组「账号生命周期」统计卡（active/cooling_down/needs_replacement 计数），本轮不默认做，用户要再加。

---

## 6. 单测案例

`tests/test_account_status.py`，纯函数，零依赖，风格同 `test_risk_status.py`。固定 `now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)`：

| # | 用例 | 输入 | 期望 |
|---|---|---|---|
| 1 | 换号优先级最高 | needs_replacement=True, cooldown_until=未来 | ("needs_replacement", "needs_replacement") |
| 2 | 冷却中（未来） | False, cooldown_until=now+3d | ("cooling_down", "cooldown") |
| 3 | 冷却已到期（过去） | False, cooldown_until=now-1d | ("active", None) |
| 4 | 无冷却 | False, cooldown_until=None | ("active", None) |
| 5 | 严格大于边界 | False, cooldown_until=now | ("active", None) |
| 6 | cooldown_count 不参与 | False, cooldown_until=未来, cooldown_count=99 | ("cooling_down", "cooldown") |

---

## 7. 修改文件清单

| 文件 | 动作 | 内容 |
|---|---|---|
| app/account.py | 新增 | `derive_account_status(needs_replacement, cooldown_until, now=None)` 纯函数 |
| tests/test_account_status.py | 新增 | 6 个单测（含边界/优先级） |
| app/query.py | 修改 | list_devices 循环内读侧派生 account_status/account_reason |
| web/src/views/Devices.vue | 修改 | 加 account_status 列 + account_reason title |

**不改**：schema.sql / ingest.py / monitor-agent / config.py / docker-compose.yml / 业务机。

---

## 8. 红线确认

- ✅ 不修改 schema.sql（account_status 列已存在，读侧派生不落库）
- ✅ 不修改 ingest.py
- ✅ 不修改 monitor-agent（数据已在 heartbeat）
- ✅ 不修改业务机（device_limit_status.json 仅读取）
- ✅ 不向 devices.account_status 落库（同 risk_status）
- ✅ 无 token 进前端 / 无新 env / 无新依赖

---

## 9. v1 不扩展确认

`banned / login_error / dead / search_limit` **不进 P2**。

原因（Phase 0 已核实）：这些状态锁死在业务机 `bridge.db.account_status.status`，且被 `/health` 污染，中央拿不到干净信号。要支持需业务机提供干净事件源（改业务机，破红线），作为 Stage 4 之后的独立议题单独决策。
