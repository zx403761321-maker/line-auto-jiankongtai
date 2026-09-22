# 敏感配置恢复说明（RESTORE）

本仓库的敏感凭据已用 GnuPG 对称加密打包为 `secrets.tar.gz.gpg`，**明文不入库**。

## 包含内容（8 个文件，按原路径）
- `.ssh/id_ed25519` — SSH 私钥
- `.claude/settings.json` — Claude Code 配置（DeepSeek 令牌）
- `.claude.json` — Claude Code 主配置
- `line-crm-monitor/.env` — 数据库密码 / INGEST_TOKEN / VIEW_TOKEN / 组账号
- `line-crm-monitor/.env.p1.bak` — 旧版环境变量备份
- `line-crm-monitor-migration/config.json` — tunn3l device_id（旧）
- `line-crm-monitor-migration/config.json.current` — tunn3l device_id（新）
- `line-crm-monitor-migration/tunn3l_data.tar.gz` — tunn3l 数据

## 解密恢复（在新服务器 / 根目录执行）
```bash
gpg --decrypt secrets.tar.gz.gpg | tar -xz -C /
```
按提示输入口令，文件会按原始相对路径解回 `/`（如 `/root/.ssh/id_ed25519`、`/root/line-crm-monitor/.env`）。

## 加密算法
- 工具：GnuPG 2.x 对称加密
- 算法：AES256
- 口令：**不在本仓库内**，请自行安全保管；丢失口令将无法解密。

## 重新加密（如更换口令）
```bash
tar -czf - -C /root \
  .ssh/id_ed25519 .claude/settings.json .claude.json \
  line-crm-monitor/.env line-crm-monitor/.env.p1.bak \
  line-crm-monitor-migration/config.json line-crm-monitor-migration/config.json.current \
  line-crm-monitor-migration/tunn3l_data.tar.gz \
  | gpg --batch --yes --pinentry-mode loopback \
      --symmetric --cipher-algo AES256 \
      --passphrase-file <口令文件> \
      --output secrets.tar.gz.gpg
```

> ⚠️ 仓库务必保持**私有**，切勿设为公开；即使公开，口令也不在仓库内，但请勿掉以轻心。
