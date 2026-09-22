---
name: line-crm-git-repo-connection
description: 监控台项目已连 GitHub，git 仓库根在 /root/line-crm-monitor 而非 /root
metadata: 
  node_type: memory
  type: project
  originSessionId: 5e210682-0dac-4dd1-8658-1fc36998cd37
  modified: 2026-09-22T06:20:18.651Z
---

line-crm 监控台项目已连接 GitHub 远程仓库 `line-auto-jiankongtai`（账号 zx403761321-maker）。

**Why:** 仓库名 `line-auto-jiankongtai`（监控台）对应本地目录 `/root/line-crm-monitor`，二者命名不一致容易混淆；且 git 仓库根目录在 `/root/line-crm-monitor`（不是 `/root`），在 `/root` 下跑 git 会看到一堆 dotfile 误以为是未跟踪文件。

**How to apply:** git 操作一律 `cd /root/line-crm-monitor`。已配 `safe.directory` 例外（目录属主是 uid 1000）。远程 token 明文存在 `.git/config`。绝不提交：`.env`、`*.bak`（含 `.env.p1.bak`）、`backup_stage7e_*.sql`、`backups/`、`tunn3l/tunn3l` 二进制、`web/node_modules|dist`、`__pycache__`。`/root/line-crm-monitor-migration/`（dump.sql/code.tar.gz/config.json 含 device_id）未纳入 git，勿提交。相关 [[line-crm-central-onboard-server]]。
