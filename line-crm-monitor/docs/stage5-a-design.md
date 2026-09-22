# Stage 5-A 设计审查：Overview 账号生命周期统计卡

> 日期：2026-08-26　阶段：设计审查（未编码）　前置：Stage 4 已部署验证

## 0. 结论

采纳 GPT 方向。**纯前端收尾，只改 `web/src/views/Overview.vue` 一个文件，零后端 / 零红线改动。**

---

## 1. API 是否需要新增统计字段

**不需要。**

理由：
- 前端 Overview 已通过 `getDevices()` 拿到全量 devices，每台已带 `account_status`（Stage 4 读侧派生，必有值）。
- Overview 现有的「风险」「运行统计」两组就是**前端聚合**（在 `groups` computed 里 `filter/reduce`），没有专门的统计 API。
- 账号生命周期组照同样模式聚合即可，新增统计字段反而破坏一致性、徒增后端改动。

---

## 2. 是否前端直接聚合 devices 数据

**是。** 复用 `getDevices()` 返回的 devices 数组，在 `groups` computed 内计数：

```js
const accActive = devices.value.filter((d) => d.account_status === 'active').length
const accCooling = devices.value.filter((d) => d.account_status === 'cooling_down').length
const accReplace = devices.value.filter((d) => d.account_status === 'needs_replacement').length
```

零后端改动。安全性：`derive_account_status` 永远返回三态之一，`account_status` 不可能为 null，三态计数之和恒等于设备总数（可作人工校验）。

---

## 3. Overview 布局调整方案

- **插入位置**：在「风险」组之后、「运行统计」组之前，插入第 4 组「账号生命周期」。调整后顺序：

  1. 基础运行（4 items）
  2. 风险（3 items）
  3. **账号生命周期（3 items）← 新增**
  4. 运行统计（4 items）

- **items（从轻到重，与风险组 normal→warning→critical 一致）**：

  | label | 对应 account_status |
  |---|---|
  | 正常 | active |
  | 冷却中 | cooling_down |
  | 需换号 | needs_replacement |

- **标签用中文**（「需换号/冷却中/正常」）而非英文枚举值：`needs_replacement` 15 字符过长，8 列卡片会溢出；且「基础运行」「运行统计」已用中文，展示友好。（可选：若坚持与「风险」组英文枚举一致，改用英文，但需调卡片宽度。）

- **样式**：复用现有 `:span="24 / g.items.length"` 自适应（3 items → 每卡 8 列）；`stat-label`/`stat-value` 纯数字，**不加颜色**，与「风险」组视觉一致。

---

## 4. 文件修改范围

| 文件 | 动作 | 内容 |
|---|---|---|
| web/src/views/Overview.vue | 修改 | `groups` computed 内新增「账号生命周期」组（3 行 filter 计数） |

**不改**：API / 后端 / 其他前端 / schema.sql / ingest.py / monitor-agent / 业务机。

---

## 5. 单测方案

**本阶段不新增单测。**

理由：
- 聚合逻辑 = 3 行 `filter().length`，风险极低。
- 项目无前端测试设施（无 Vitest/Jest），为 3 行逻辑引入测试框架属过度工程（Stage 3/4 单测都是后端 Python 纯函数，本阶段无对应后端逻辑）。
- **替代验证**（部署后人工）：Overview 账号卡 3 个数字之和 = 设备总数（15），且三态计数分别 == Devices 页对应 tag 计数（需换号 4 / 冷却中 2 / 正常 9）。

---

## 6. 红线确认

- ✅ 不修改 schema.sql / ingest.py / monitor-agent / 业务机
- ✅ 纯前端，无 token / 无新依赖 / 无新 env

---

## 7. 补充（GPT 建议，已采纳）

- 告警系统**暂缓**，单独作为后续 Stage 设计。
- banned / login_error / dead / search_limit **不扩展**，保持当前红线。
