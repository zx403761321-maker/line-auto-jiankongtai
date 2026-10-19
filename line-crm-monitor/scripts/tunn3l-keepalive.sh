#!/usr/bin/env bash
# 中央监控 tunn3l 隧道保活（由宿主 systemd timer 调用：line-monitor-tunn3l-keepalive.timer）
#
# 背景：tunn3l.sh 免费固定子域名每隔 3~7 天会被服务端断开一次。正常时客户端会
#       自动重连；但偶发会卡在「假在线」——服务端已释放子域名、客户端却不再重连，
#       此时公网访问返回 404 "No tunnel found for subdomain: <name>"。
#
# 做法：周期性探测公网 URL，非 200 即重启 tunn3l 容器强制重连。
#       带 30 分钟冷却，避免隧道彻底不可用时每 5 分钟反复重启刷屏。
#
# 用法： ./scripts/tunn3l-keepalive.sh   （由 systemd 定时调用，非手工）
set -uo pipefail          # 刻意不用 -e：探测失败要用退出码表达，而非中断脚本

cd "$(dirname "$0")/.."   # 切到项目根目录

SUBDOMAIN="$(grep -E '^TUNN3L_SUBDOMAIN=' .env | head -1 | cut -d= -f2-)"
[ -n "${SUBDOMAIN:-}" ] || SUBDOMAIN="line-monitor"
URL="https://${SUBDOMAIN}.tunn3l.sh/"
SERVICE="tunn3l"
TIMEOUT=15
COOLDOWN=1800                            # 两次重启最短间隔（秒）
MARKER="/tmp/tunn3l-keepalive.lastrestart"

now()   { date -u +%s; }
log()   { echo "[$(date -u '+%F %T UTC')] $*"; }

probe() {                                # 输出 HTTP 状态码；失败/无响应输出 000
  local c
  c="$(curl -sS -m "$TIMEOUT" -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)" || c="000"
  echo "${c:-000}"
}

CODE="$(probe)"
if [ "$CODE" = "200" ]; then
  exit 0                                 # 健康，静默退出
fi

# —— 以下为故障路径 ——
LAST="$(cat "$MARKER" 2>/dev/null || echo 0)"
NOW="$(now)"
if [ $((NOW - LAST)) -lt "$COOLDOWN" ]; then
  log "仍不可达 HTTP=${CODE}，距上次重启 $((NOW - LAST))s < ${COOLDOWN}s，跳过本轮重启"
  exit 0
fi

log "探测失败 HTTP=${CODE}，重启 $SERVICE 强制重连"
if ! docker compose restart "$SERVICE"; then
  log "ERROR: docker compose restart $SERVICE 失败"
  exit 1
fi

echo "$NOW" > "$MARKER"
sleep 12                                 # 等隧道重连
CODE2="$(probe)"
log "重启完成，复测 HTTP=${CODE2}"

# 复测仍失败给一条明确告警，退出码保持 0（下一轮 timer 会再尝试）
[ "$CODE2" = "200" ] || log "WARN: 重启后仍非 200，将在下一轮（>=${COOLDOWN}s 后）再次重启"
exit 0
