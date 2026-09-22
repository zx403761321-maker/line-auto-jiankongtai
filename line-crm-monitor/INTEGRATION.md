# JP-01 联调 Runbook（步骤 6）

## A. 部署中央（本地电脑）

```bash
# 1. 把 /root/line-crm-monitor/ 拷到本地电脑
# 2. 配置
cp .env.example .env      # 填 POSTGRES_PASSWORD / INGEST_TOKEN（建议也设 VIEW_TOKEN）
# 3. 启动
docker compose up -d --build
# 4. 验证
curl http://localhost:8000/health     # -> {"ok":true}
```

## B. 配置业务机 JP-01

编辑 `/root/line-crm/config/monitor.yaml`：

- `monitor_url` → 中央实际地址（局域网 IP / Tailscale / 反代 HTTPS）
- `ingest_token` → 与中央 `INGEST_TOKEN` 一致

## C. 部署业务机

```bash
cd /root/line-crm
docker compose up -d --build monitor-agent   # 起上报代理
docker compose up -d --build adb-bridge       # 重建镜像：让新 main.py 的 append_event 生效
docker logs -f openclaw-monitor-agent         # 看上传日志
```

> ⚠️ 重要：`main.py` 是被 `COPY . .` 烤进 adb-bridge 镜像的，compose 里没有挂载源码目录。
> 因此只要 `main.py`（或任何源码）发生变化，必须用 `docker compose up -d --build adb-bridge`
> 重建镜像；单纯 `docker compose restart adb-bridge` 只会重启旧容器，不会加载新代码。

## D. 验证清单

- [ ] 中央 `/health` 返回 200
- [ ] agent 日志出现 `上传成功 N 条事件`
- [ ] `GET /api/servers` 出现 `JP-01` 且 `online=true`
- [ ] `GET /api/devices` 出现 `cloud-*`，`online_status` 有值
- [ ] `needs_replacement=true` 的正好是 cloud-07/10/13/14（4 台；cloud-01/11 已换号，cloud-08/09 cooling_down）
- [ ] 幂等：同一 `event_id` 重发，`events` 表不新增（`ON CONFLICT DO NOTHING`）

## E. 常见排查

| 现象 | 原因 |
|---|---|
| `401 invalid ingest token` | 业务机 `ingest_token` 与中央 `INGEST_TOKEN` 不一致 |
| `503 INGEST_TOKEN not configured` | 中央 `.env` 没设 `INGEST_TOKEN` |
| 上传失败 connection refused / timeout | `monitor_url` 不可达（防火墙/网络不通） |
| `online=false` 一直 | 中央 `agent_last_seen_at` 超 300s，agent 没在跑 |
| 设备 online_status 为 null | `/health` 还没被调用（等 ≤30s），或 adb-bridge 未重建镜像（需 `--build`） |

## 开放项（P1 已知，待定方案）

- **JSONL 无轮转**：`monitor_events.jsonl` 只追加不删除，且 agent 挂载 `./data:/data:ro`
  无法截断，长期会无限增长（P1 量约 3MB/天）。需定轮转方案：main.py 侧按大小轮转，
  或宿主机 logrotate。建议在下轮编码前定掉。
