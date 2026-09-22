---
name: line-crm-central-onboard-server
description: 中央监控接入新业务服务器的中央侧固定套路（3 个 .env 键 + 重启 + 中文组名坑）
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d9a2de0-f3cb-4b9c-b8c3-221b333357bd
  modified: 2026-09-08T03:40:25.701Z
---

中央监控接入一台新业务服务器（如 JP-05/JP-06）后，中央侧要做的是改 `/root/line-crm-monitor/.env` 的 3 个键，然后重启。命名约定统一为 `jp0X-*`：

- `SERVER_IP_MAP`：加 `"JP-0X":"<公网IP>"`（Dashboard 展示用）
- `SERVER_GROUP_MAP`：加 `"JP-0X":"jp0X-view"`（权限归属）
- `GROUP_USERS`：加 `"jp0X_viewer":{"password":"jp0X_<公网IP>","group_id":"jp0X-view"}`（只读账号；密码=前缀+IP）

改完重启：`docker compose up -d --force-recreate api tunn3l`（必须 api+tunn3l 一起，见 [[line-crm-tunn3l-network-recreate]]）。`seed_users` 在启动时（`init_schema` → `users.seed_users`）幂等执行：自动建组、建用户、`UPDATE servers SET group_id` 把新服务器从 default 迁到 jp0X-view；`ON CONFLICT DO NOTHING` 不覆盖已有数据，重启安全。

**坑**：`seed_users` 新建的组 `name` = `id`（英文，如 "jp05-view"），但 jp01~jp04 的中文名「JP-0X 只读」是当初手工 `UPDATE groups SET name` 设的。所以每次新接入后要补一句：
`UPDATE groups SET name='JP-0X 只读' WHERE id='jp0X-view';`

验证只读隔离：用 `jp0X_viewer` 登录后 `/api/servers` 只返回 JP-0X，`/api/devices` 只返回该服务器设备。
