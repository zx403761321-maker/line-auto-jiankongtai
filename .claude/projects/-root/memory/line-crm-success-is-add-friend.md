---
name: line-crm-success-is-add-friend
description: daily_statistics.success / today_success 的语义是「LINE 加好友成功次数」
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d9a2de0-f3cb-4b9c-b8c3-221b333357bd
  modified: 2026-09-07T07:49:05.685Z
---

中央监控（/root/line-crm-monitor）里 `today_success`（业务机 `account_status.daily_success`）与 `daily_statistics.success` 的语义就是「LINE 加好友成功次数」（owner 确认），不是混了多种任务的通用成功数。周累计添加 / 月累计添加即聚合该字段，无需业务侧再加类型区分。
