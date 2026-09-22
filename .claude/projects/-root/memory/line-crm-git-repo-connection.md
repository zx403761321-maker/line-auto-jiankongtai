---
name: line-crm-git-repo-connection
description: 整机配置备份已推 GitHub（repo 根=/root，敏感文件 gpg 加密，口令不在仓库）
metadata: 
  node_type: memory
  type: project
  originSessionId: 5e210682-0dac-4dd1-8658-1fc36998cd37
  modified: 2026-09-22T07:12:49.922Z
---

line-crm 相关整机固定配置已备份到 GitHub 私有仓库 `line-auto-jiankongtai`（账号 zx403761321-maker）。

**Why:** 仓库根目录在 `/root`（不是 `/root/line-crm-monitor`）。敏感凭据（SSH 私钥、`.env`、`.claude.json`/`.claude/settings.json`、tunn3l device_id）用 gpg AES256 对称加密打包成 `/root/secrets.tar.gz.gpg`，明文不入库。**加密口令不在仓库内**，需向用户索要（别写进 memory，memory 会被明文提交）。

**How to apply:** git 操作 `cd /root`（repo 根）。重建恢复：`gpg --decrypt secrets.tar.gz.gpg | tar -xz -C /`，详见 RESTORE.md。明文绝不提交：`.ssh/id_ed25519`、`.claude.json`、`.claude/settings.json`、`.bash_history`、`.docker/`、`.config/`、`line-crm-monitor/.env`+`.env.p1.bak`、migration 的 config.json/config.json.current/tunn3l_data.tar.gz。同时排除：`backups/`、`backup_stage7e_*.sql`、`dump.sql`、`code.tar.gz`、`.vscode-server`、`node_modules`、`.claude` 会话缓存。相关 [[line-crm-central-onboard-server]]。
