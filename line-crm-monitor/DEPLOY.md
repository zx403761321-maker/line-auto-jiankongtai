# Stage 2 部署说明（给 open claw）

> 目标：把 P2 的 Vue3 Dashboard 前端 + 登录鉴权，部署到**用户本地电脑**的中央监控项目里。
> P1（后端 + JP-01 联调）已上线并冻结，本次**只新增前端、读侧鉴权、静态托管**，不动 schema/ingest/agent/业务机。

---

## ⚠️ 已知风险（已接受，勿擅自修改）

> 记录日期：2026-09-04　决策人：项目 owner

**风险：公网暴露 + 弱口令。**

- 本服务经 tunn3l 公网隧道（子域 `line-monitor`）暴露，登录入口 `POST /api/auth/login`
  与 Dashboard 均公网可达。
- 管理员口令为弱口令（见 `.env` 的 `ADMIN_PASSWORD`，非随机强口令）。
- 叠加后果：任何能访问该公网地址的人，一次尝试即可猜中管理员口令并登录。

**owner 的明确决定（2026-09-04）：**
1. 不更换口令；
2. 不更换公网网址 / 不关闭隧道；
3. 不增加 2FA / 二次验证。

**约束：**
- 该风险被**主动接受**，不视为待修复缺陷。
- 后续接手者**不得在未与 owner 重新确认前**，擅自改口令、改网址或加验证，
  以免破坏 owner 现有登录习惯与已分发地址。
- 若日后决定收紧，参考 README「鉴权（fail-closed）」；当前 `config.py` 的
  `ensure_public_safe()` 只校验 `SESSION_SECRET` 长度与账号存在，**不校验口令强度**。

---

## 0. 前提

- 中央项目目录（下称 `<中央>`）里已有 P1 的 `docker-compose.yml`、`app/`、`schema.sql`、`.env`（含 `POSTGRES_PASSWORD`、`INGEST_TOKEN`）。
- 数据库 `pgdata` 卷已存在且有数据（**不要重建 db 卷**，否则丢 P1 数据）。

## 1. 解压覆盖

```bash
tar xzf line-crm-monitor.tar.gz -C <中央>/
```

覆盖项：`Dockerfile`、`docker-compose.yml`、`requirements.txt`、`app/`、`web/`、`.env.example`、`.gitignore`、`.dockerignore`。
不动项：`.env`（打包时已排除，你的 token 不会被覆盖）。

## 2. 配置 .env（重点：查 / 改 VIEW_TOKEN）

### 2.1 查看当前值

```bash
grep -E '^(VIEW_TOKEN|SESSION_SECRET|INGEST_TOKEN|POSTGRES_PASSWORD)=' <中央>/.env
```

- `VIEW_TOKEN=` 为空 → 读接口/网页**开放访问，无登录框**（适合本机/纯局域网测试）。
- `VIEW_TOKEN=xxx` → 打开网页会弹登录框，密码就是 `xxx`。

### 2.2 修改 VIEW_TOKEN

用编辑器打开 `<中央>/.env`，改这一行：

```bash
# 设置一个登录密码（推荐，尤其暴露到局域网/Tailscale 前）
VIEW_TOKEN=我的新密码

# 或者留空 = 开放访问（不要在有外部暴露风险时这么做）
VIEW_TOKEN=
```

改完后**必须重建/重启 api 容器**才生效（配置在启动时读取）：

```bash
cd <中央> && docker compose up -d --build api
```

### 2.3 SESSION_SECRET

`SESSION_SECRET=` 建议填一个随机字符串（登录 cookie 签名用），否则留空时每次重启会用随机密钥、已登录会掉线重新登录。

```bash
# 生成一个随机值并追加到 .env（若已存在可跳过）
grep -q '^SESSION_SECRET=' <中央>/.env && echo "已有 SESSION_SECRET" \
  || printf '\nSESSION_SECRET=%s\n' "$(head -c 24 /dev/urandom | base64)" >> <中央>/.env
```

> ⚠️ 安全红线：`VIEW_TOKEN` / `INGEST_TOKEN` / `POSTGRES_PASSWORD` **绝不写进前端 JS 或任何示例文件**，只存在 `.env`，且 `.env` 不进 Git。

## 3. 构建并启动

```bash
cd <中央>
docker compose up -d --build        # 多阶段：node:20-alpine 构建前端 → python:3.12-slim 运行
```

首次构建前端要 `npm ci`，会下载依赖，稍慢属正常。

## 4. 验证

```bash
curl http://localhost:8000/health            # -> {"ok":true}
curl -o /dev/null -w '%{http_code}\n' http://localhost:8000/   # -> 200（返回 index.html）
```

浏览器打开 `http://localhost:8000/`：
- 看到侧边栏 3 个页面（总览 / 服务器 / 设备）→ 前端构建产物已正确托管。
- 若 `.env` 里 `VIEW_TOKEN` 非空 → 弹登录框，输入该值即可；留空 → 直接进入。
- 三页数据 = 前端聚合读 `/api/servers` + `/api/devices`（读接口走 `Authorization: Bearer <VIEW_TOKEN>` 或已登录 session cookie）。

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 页面空白、控制台 404 `/assets/...` | 前端没构建成功，看 `docker compose build` 的 `npm run build` 报错 |
| 打开首页却一直转圈 / 401 | `.env` 的 `VIEW_TOKEN` 与登录输入不一致，或改了 `.env` 没 `--build` 重启 api |
| 登录成功但刷新又掉线 | `SESSION_SECRET` 为空，重启后密钥变了；按 2.3 固定一个值 |
| `docker compose up` 报 `set VIEW_TOKEN` 类错误 | 旧 compose 引用不存在；确认用的是本次包里新版 `docker-compose.yml` |
| 改 `.env` 不生效 | 一定是漏了 `--build`（环境变量进容器镜像/启动参数，普通 `restart` 不重读） |

## 6. 回滚

```bash
# 仅前端/鉴权有异常，回退到 P1 后端（不丢数据）：
cd <中央>
git checkout -- Dockerfile docker-compose.yml requirements.txt app/ 2>/dev/null || true   # 如有 git
docker compose up -d --build   # 用回 P1 代码重建
```

数据在 `pgdata` 卷里，回滚前端**不影响**任何已入库数据。

---

## 7. 备份

- `scripts/backup.sh`：`docker compose exec -T db pg_dump | gzip` 到 `backups/`，仅保留最近 7 份。
- 每日定时由 **systemd timer** 执行（本机无 cron）：单元文件在
  `/etc/systemd/system/line-monitor-backup.{service,timer}`，`OnCalendar=*-*-* 19:00:00`（宿主 UTC =
  台北 03:00，避开业务高峰）；`Persistent=true` 保证停机错过时开机补跑。
  日志追加写 `backups/backup.log`。换机复现：
  `cp` 这两个 unit 文件 → `systemctl daemon-reload && systemctl enable --now line-monitor-backup.timer`。
- ⚠️ **这是「同机备份」，只防逻辑损失（误 DROP / 坏迁移），不防磁盘故障**。真正的灾备需把
  `backups/` 再同步到异地（后续项，未实现前不要误认为已有灾备）。
