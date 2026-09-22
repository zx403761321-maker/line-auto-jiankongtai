"""中央监控 FastAPI 配置（全部来自环境变量，无硬编码域名/IP）。"""
import json
import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_json_map(name: str) -> dict:
    """解析 JSON 环境变量为 dict（如 SERVER_IP_MAP）；缺失/解析失败返回空 dict。"""
    raw = _env(name, "")
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return {str(k): str(v) for k, v in val.items()} if isinstance(val, dict) else {}


def _env_json(name: str):
    """解析 JSON 环境变量为原生结构（保留嵌套 dict/list）；缺失/解析失败返回 None。"""
    raw = _env(name, "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


DATABASE_URL = _env("DATABASE_URL", "postgresql://monitor:monitor@localhost:5432/monitor")

# 鉴权（fail-closed）：写入必填；读接口可选（暴露到局域网/Tailscale 前建议设置）
INGEST_TOKEN = _env("INGEST_TOKEN", "")
VIEW_TOKEN = _env("VIEW_TOKEN", "")

# 登录会话 cookie 签名密钥（不设则每次重启登录态失效；生产建议在 .env 设置）
SESSION_SECRET = _env("SESSION_SECRET", "")

# agent_last_seen_at 超过该秒数判离线
STALENESS_SECONDS = float(_env("STALENESS_SECONDS", "300"))

# events 保留天数（cleanup 后台任务按 event_type 分批删除过期事件；0 = 不清理）
EVENT_RETENTION_DAYS = {
    "device_status": int(_env("RETENTION_DEVICE_STATUS_DAYS", "30")),
    "heartbeat": int(_env("RETENTION_HEARTBEAT_DAYS", "30")),
    "task_result": int(_env("RETENTION_TASK_DAYS", "90")),
    "error_event": int(_env("RETENTION_TASK_DAYS", "90")),
}

# risk_status 判定阈值（读侧派生；环境变量优先，默认 40/90）
RISK_WARNING_THRESHOLD = int(_env("RISK_WARNING_THRESHOLD", "40"))
RISK_CRITICAL_THRESHOLD = int(_env("RISK_CRITICAL_THRESHOLD", "90"))

# CORS 允许来源（逗号分隔）；"*" = 允许所有（P1 默认，接 Vue 前收紧）
CORS_ORIGINS = _env("CORS_ORIGINS", "*")

# server_id → 公网 IP 静态映射（读侧派生，供 Dashboard 展示；新增服务器手动补充）
SERVER_IP_MAP = _env_json_map("SERVER_IP_MAP")

# server_id → group_id 归属映射（权限底座；未列出的服务器默认归 'default'）
SERVER_GROUP_MAP = _env_json_map("SERVER_GROUP_MAP")

# ── 权限底座（Stage7-E）──────────────────────────────────────────────
# admin 账号（seed 用；未设 ADMIN_PASSWORD 则不创建）
ADMIN_USERNAME = _env("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "")

# group 用户（JSON：{"用户名":{"password":"...","group_id":"default"}}）
GROUP_USERS = _env_json("GROUP_USERS") or {}

# 公网模式：控制 https_only + 启动 fail-closed 检查（Phase F 启用）
PUBLIC_MODE = _env_bool("PUBLIC_MODE", False)


def ensure_public_safe() -> None:
    """PUBLIC_MODE=true 的安全前提（fail-closed，不满足直接启动失败）：
    1. SESSION_SECRET ≥32 字符（否则 cookie 签名密钥每次重启随机 → 登录态丢失且可伪造）
    2. 至少一个可登录账号（ADMIN_PASSWORD 或 GROUP_USERS），否则公网无人能登录
    """
    if not PUBLIC_MODE:
        return
    if not SESSION_SECRET or len(SESSION_SECRET) < 32:
        raise RuntimeError(
            "PUBLIC_MODE=true 要求 SESSION_SECRET ≥32 字符（持久且保密）；"
            "请在 .env 用 `openssl rand -hex 32` 生成后重启"
        )
    if not ADMIN_PASSWORD and not GROUP_USERS:
        raise RuntimeError(
            "PUBLIC_MODE=true 要求至少一个可登录账号：设 ADMIN_PASSWORD 或 GROUP_USERS"
        )
