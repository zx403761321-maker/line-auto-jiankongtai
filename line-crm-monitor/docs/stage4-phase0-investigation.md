# Stage 4 Phase 0 调查报告：account_status 数据源与状态语义

> 日期：2026-08-26　阶段：只读调查（未写任何代码）　范围：业务机 `/root/line-crm` 源码

## 0. 调查方法

只读，读了 6 个业务源码文件 + 若干全仓 grep：

| 文件 | 角色 |
|---|---|
| services/adb-bridge/account_manager.py | bridge.db `account_status` 表的唯一写入者 |
| services/adb-bridge/main.py | `/health`、`append_event`、任务上报、启动连接 |
| services/adb-bridge/scheduler.py | 选号逻辑（状态语义的权威消费者） |
| services/adb-bridge/db.py | 另一套 `device_status`/`task_log`/`reply_log` 表 |
| services/monitor-agent/collect.py | heartbeat 设备快照的字段源映射 |
| scripts/template.sh | `device_limit_status.json` 的唯一写入者 |
| config/monitor.yaml | agent 路径/server_id 配置 |

---

## 1. 数据源关系图（核心结论）

业务机存在**两套完全独立的"账号状态"系统**，各自维护、互不通信，只有 `device_id` 能对上号：

```
业务机 (JP-01)
├── bridge.db :: account_status          (Python account_manager.py 写)
│     status ∈ active / online / offline / cooldown / search_limit /
│              login_error / dead / banned  (+ disabled/paused 仅保留未写)
│     └─ 被 /health 每 30s 冲成 online/offline  ← 污染
│
├── device_limit_status.json             (scripts/template.sh 写，非 Python)
│     status ∈ active / cooling_down / needs_replacement
│     └─ 唯一干净、不受 /health 污染的账号生命周期信号
│
└── bridge.db :: device_status 表        (db.py record_device_status)
      └─ 死代码：init_db()/record_device_status() 从未被调用

中央监控 monitor-agent (collect_snapshot)
├── 读 bridge.db:  today_success←daily_success, today_fail←daily_fail,
│                  risk_score, last_task_at      ← 只读 4 列，不读 status
└── 读 device_limit_status.json: cooldown_count, cooldown_until,
                                  needs_replacement
```

**关键发现**：`collect.py` 根本不读 bridge.db 的 `status` 字段。中央目前对账号生命周期唯一的可见信号 = device_limit_status.json 的 `needs_replacement / cooldown_count / cooldown_until`。

---

## 2. 数据权威链路（谁写、何时、覆盖关系、冲突优先级）

### bridge.db.account_status.status 所有写入点

| 写入点 | 触发时机 | 写入值 |
|---|---|---|
| `ensure_account` | 首次 INSERT | active |
| `update_status(status=...)` | 通用 setter | 任意 |
| **`/health`** | **每 30s（docker healthcheck）对每台设备** | **online / offline ← 污染源** |
| **`_startup_connect_devices`** | **进程启动** | **online / offline ← 污染源** |
| `record_success` | add_friend 成功 | （不改 status，仅清 consecutive_fails / cooldown_until） |
| `record_failure` | add_friend 失败 | （不改 status，超阈值 → enter_cooldown） |
| `enter_cooldown` | 连续失败 ≥ 10 | cooldown |
| `exit_cooldown` | 手动 | active |
| `_apply_search_limit` | 搜索结果 = search_limit | search_limit |
| `_apply_login_error` | 登录失败 | login_error |
| `_apply_dead` | 设备离线 | dead |
| `_apply_banned` | 账号被封 | banned |
| `_apply_no_result` | 用户不存在 | （不改 status，仅 today_not_found+1） |
| `_maybe_reset_daily` | 跨天 | search_limit → active |

### 覆盖关系（本次调查最重要的发现）

`/health`（+ 启动）**每 30 秒无条件** `am.update_status(status="online"/"offline")`，会**覆盖** `report()` 刚写入的 search_limit / banned / dead / login_error / cooldown。

> 时序：任务执行 `report()` 写入真实状态 → 最多 30s 后 `/health` 把它冲回 online/offline。

**结论：bridge.db.account_status.status 在绝大多数采样时刻 = online/offline，真实账号状态只在任务瞬间短暂存活。此字段不可作为中央监控 account_status 的权威源。**

### device_limit_status.json.status 写入点（唯一）

- 只有 `template.sh::mark_search_limit()` 写（全仓 grep 确认无第二写入点）。
- 触发：每日加好友循环 `error == "search_limit"` 时 `cooldown_count + 1`；≥ 3 次 → `needs_replacement`，否则 `cooling_down`。
- 用户换号后手动重置为 active（见换号记忆）。
- 该文件与 `/health` 无关，**不受污染**。

### 冲突优先级（跨两套源）

两套源互不写对方，无直接冲突。但语义有重叠：bridge.db 的 `search_limit` 与 device_limit 的 `cooling_down` 都源于"搜索上限"，只是 bridge.db 是瞬时态（会被冲掉），device_limit 是累积态（持久可靠）。

---

## 3. 状态枚举表 + 业务含义

### bridge.db.account_status.status（生产实际写入的 9 值）

| 值 | 写入者 | 业务含义 | 备注 |
|---|---|---|---|
| active | 默认 / exit_cooldown / 跨天 | 正常可执行 | |
| online | /health、启动 | adb 可达 | **污染值，非账号语义** |
| offline | /health、启动 | adb 不可达 | **污染值，非账号语义** |
| cooldown | enter_cooldown | 连续失败 ≥10 → 冷却 30min | 与 device_limit 冷却是两回事 |
| search_limit | _apply_search_limit | 今日搜索达上限，冷却到明早 | 跨天自动 → active |
| login_error | _apply_login_error | LINE 登录失败 | 需人工 |
| dead | _apply_dead | 设备离线 / ADB 连接失败 | 需人工 |
| banned | _apply_banned | 账号被封 | 需人工 |
| disabled | （无写入者） | 人工禁用 | 保留未实现，仅 scheduler 读 |
| paused | （无写入者） | 人工暂停 | 保留未实现，仅 scheduler 读 |

### device_limit_status.json.status

| 值 | 写入者 | 业务含义 |
|---|---|---|
| active（或缺省） | 默认 / 用户重置 | 正常 |
| cooling_down | template.sh | 第 1~2 次触顶，冷却 5 天 |
| needs_replacement | template.sh | 第 3 次触顶，需换号 |

---

## 4. 业务原始状态 vs 中央展示状态（区分）

- **业务原始状态**（业务机侧，用于业务控制逻辑）：
  - bridge.db.status：被 /health 污染，实际承载的是"adb 可达性"而非"账号生命周期"。
  - device_limit_status.json.status：真正的账号生命周期决策（要不要换号）。
- **中央展示状态**（中央 devices 表，用于展示/报警）：
  - `online_status`：P1 已维护（= adb 可达）。
  - `risk_status`：Stage 3 已实现（读侧派生 normal/warning/critical）。
  - `account_status`：Stage 4 目标 —— 应从 device_limit_status.json 派生，而非 bridge.db.status（后者被污染）。
- **核心区分**：中央 account_status 不应试图复刻 bridge.db 那个已被污染的 status，而应以 device_limit_status.json（唯一干净源）为准，叠加 risk_status 已有信息。

---

## 5. 状态变化 / 历史字段（为 Stage 5 预留）

- bridge.db.account_status：只有 `created_at / updated_at / last_error_at`（REAL epoch）。**无 status_changed_at，无 history 表**。
- bridge.db.device_status（db.py）：本是有 `recorded_at + status` 的上下线历史表，但 `init_db() / record_device_status()` 从未被调用 = **死代码**。
- device_limit_status.json：有 `updated`（ISO 字符串），无历史。
- **结论**：业务侧当前没有任何可用的 account_status 变化历史来源。中央 devices 表虽已预留 `account_status_changed_at`（schema），但业务侧喂不了数据；Stage 5 若要"状态变化时间轴"，需业务侧补（改业务代码，超出当前红线）。

---

## 6. 可由现有 heartbeat 推导出的状态（零改动可实现）

现有 heartbeat 快照已含 3 个账号相关字段：`needs_replacement / cooldown_count / cooldown_until`。可直接读侧派生三态：

| 派生 account_status | 判据 |
|---|---|
| needs_replacement | needs_replacement == true |
| cooling_down | needs_replacement == false 且 cooldown_count > 0 且冷却未到期 |
| active | 其余 |

→ 这就是 v1 最小集，**零 agent / schema / ingest 改动**。

---

## 7. 当前无法推导但业务存在的状态

这些真实账号异常态业务侧确实会写，但中央拿不到（要么不被采集，要么被污染）：

| 状态 | 为什么拿不到 |
|---|---|
| search_limit | 在 bridge.db.status，被 /health 冲掉 + collect 不采集 |
| banned | 同上 |
| login_error | 同上 |
| dead | 同上 |
| cooldown（连续失败冷却） | 同上 |
| daily_limit（今日加满） | 可由 daily_success ≥ daily_add_limit 推导，但 daily_add_limit 不采集 |
| disabled / paused | 业务侧就没实现写入 |

---

## 8. v1 建议 account_status 集合（不冻结，供 Phase 1 讨论）

建议 v1 = 3 态：**`active / cooling_down / needs_replacement`**

- 理由：全部来自 device_limit_status.json（唯一可靠源），读侧派生零改动，符合 P2 红线。
- 不纳入：search_limit / banned / login_error / dead（拿不到可靠信号；强拿要么改业务机修 /health 污染，要么改 agent 采一个被污染的字段，均触碰红线）。

---

## 9. 是否需要修改 agent / 业务机（评估）

- **v1（active/cooling_down/needs_replacement）：完全不需要。** 数据已在 heartbeat 里。
- **若要更细账号异常（banned/search_limit/dead 等）：绕不开改业务机**，因为：
  1. bridge.db.status 被 /health 污染，采了也没用；
  2. 唯一干净的 device_limit_status.json 只表达"换号"维度，不表达"封号/登录异常/设备死"；
  3. 真正要拿到这些，需改 main.py（把 online/offline 从 account_status.status 剥离，或账号状态变化时 append_event）—— 这属于"改业务服务器"，超出 P2 红线，需用户单独决策。

---

## 关键结论 / 风险提示

1. **最大发现**：bridge.db 的 account_status.status 被 /health 每 30s 冲成 online/offline，本质不可信；真正干净的账号生命周期源是 device_limit_status.json。
2. **v1 落地零改动**：active / cooling_down / needs_replacement 三态全部可由现有 heartbeat 读侧派生（同 Stage 3 手法，纯函数）。
3. **更深状态被红线卡住**：封号 / 登录异常 / 设备死等真实异常态，业务机没有干净导出，中央拿不到；若要支持，必须改业务机（破红线），需用户拍板是否作为 Stage 4 之后的独立议题。
