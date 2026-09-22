---
name: line-crm-host-no-npm-cron
description: 中央监控宿主机无 npm/cron，前端依赖与定时备份的替代做法
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d9a2de0-f3cb-4b9c-b8c3-221b333357bd
  modified: 2026-09-07T07:49:08.168Z
---

中央监控宿主机（/root/line-crm-monitor）**没装 npm 也没有 cron**（systemd 是 PID 1）。前端加依赖用 `docker run --rm -v /root/line-crm-monitor/web:/web -w /web node:20-alpine npm install <pkg>`；每日备份走 systemd timer `line-monitor-backup.timer`（`OnCalendar=*-*-* 19:00:00` UTC = 台北 03:00，日志追加 `backups/backup.log`）。前端 Docker 构建用 `npm ci`，改 package.json 必须同步更新 package-lock.json。
