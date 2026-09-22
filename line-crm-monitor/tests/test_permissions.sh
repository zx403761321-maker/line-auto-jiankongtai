#!/bin/bash
# Stage7-E 权限回归测试（admin / group / 401 / 404 / token）
# 前置：Phase A(seed) + Phase B(登录) + Phase C(过滤) 已部署
# group 场景需先在 .env 配 GROUP_USERS 并重建 api（见部署指令）
# 用法（env 传参，避免密码进命令行历史）：
#   BASE=http://localhost:8000 ADMIN_PASS=xxx GROUP_USER=组长 GROUP_PASS=yyy VIEW_TOKEN=zzz bash tests/test_permissions.sh
set -u

BASE="${BASE:-http://localhost:8000}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-}"
GROUP_USER="${GROUP_USER:-}"
GROUP_PASS="${GROUP_PASS:-}"
VIEW_TOKEN="${VIEW_TOKEN:-}"

TMP=$(mktemp -d)
PASS=0; FAIL=0
ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "======== 权限回归测试 ========"

echo "[1] admin 登录 + 全量"
code=$(curl -s -o "$TMP/a.json" -w '%{http_code}' -c "$TMP/a.jar" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
[ "$code" = 200 ] && ok "admin 登录 200" || bad "admin 登录 期望200 实际$code"
n=$(curl -s -b "$TMP/a.jar" "$BASE/api/servers" | python3 -c "import sys,json;print(len(json.load(sys.stdin).get('servers',[])))" 2>/dev/null)
echo "      admin 可见 $n 台"
[ -n "$n" ] && [ "$n" -ge 2 ] && ok "admin 全量≥2" || bad "admin 全量异常(n=$n)"

echo "[2] 401 错误密码"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"$ADMIN_USER\",\"password\":\"WRONG-PASSWORD\"}")
[ "$code" = 401 ] && ok "错误密码 401" || bad "错误密码 期望401 实际$code"

echo "[3] token 直连（系统只读全量）"
if [ -n "$VIEW_TOKEN" ]; then
  code=$(curl -s -o "$TMP/t.json" -w '%{http_code}' -H "Authorization: Bearer $VIEW_TOKEN" "$BASE/api/servers")
  [ "$code" = 200 ] && ok "token 200" || bad "token 期望200 实际$code"
  tn=$(python3 -c "import json;print(len(json.load(open('$TMP/t.json')).get('servers',[])))" 2>/dev/null)
  echo "      token 可见 $tn 台"
else
  echo "  ⏭️ 未设 VIEW_TOKEN，跳过 token 场景"
fi

echo "[4] group 用户登录 + 限制 + 越权 404"
if [ -n "$GROUP_USER" ] && [ -n "$GROUP_PASS" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -c "$TMP/g.jar" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"$GROUP_USER\",\"password\":\"$GROUP_PASS\"}")
  [ "$code" = 200 ] && ok "group 登录 200" || bad "group 登录 期望200 实际$code"
  gids=$(curl -s -b "$TMP/g.jar" "$BASE/api/servers" | python3 -c "import sys,json;print(','.join(s['server_id'] for s in json.load(sys.stdin).get('servers',[])))" 2>/dev/null)
  echo "      group 可见: $gids"
  # 越权：不存在 server（与「非本组」统一 404，防枚举）
  code=$(curl -s -o /dev/null -w '%{http_code}' -b "$TMP/g.jar" "$BASE/api/servers/JP-999")
  [ "$code" = 404 ] && ok "group 访问不存在/越权 server 404" || bad "越权 server 期望404 实际$code"
  # 设备越权：显式 server_id 非本组 → 404（不返回空列表，防信息泄露）
  code=$(curl -s -o /dev/null -w '%{http_code}' -b "$TMP/g.jar" "$BASE/api/devices?server_id=JP-999")
  [ "$code" = 404 ] && ok "group 设备越权 404" || bad "设备越权 期望404 实际$code"
else
  echo "  ⏭️ 未设 GROUP_USER/GROUP_PASS，跳过 group 场景"
fi

echo ""
echo "======== 结果: PASS=$PASS FAIL=$FAIL ========"
rm -rf "$TMP"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
