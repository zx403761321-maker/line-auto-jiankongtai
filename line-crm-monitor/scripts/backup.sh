#!/usr/bin/env bash
# 中央监控 PostgreSQL 每日备份（由宿主 systemd timer 调用：line-monitor-backup.timer）
# 用法：  ./scripts/backup.sh
#
# 注意：这是「同机备份」，只防逻辑损失（误 DROP / 坏迁移），不防磁盘故障。
#       真正的灾备需把 backups/ 再同步到异地（后续项，见 DEPLOY.md）。
set -euo pipefail

cd "$(dirname "$0")/.."           # 切到项目根目录
BACKUP_DIR="backups"
KEEP=7                            # 只保留最近 7 份

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M%S)"
FILE="$BACKUP_DIR/backup_${STAMP}.sql.gz"

# docker compose 服务名为 db（勿写死容器名）；exec -T 关闭 TTY 以便重定向
docker compose exec -T db pg_dump -U monitor -d monitor | gzip > "$FILE"

echo "备份完成: $FILE ($(du -h "$FILE" | cut -f1))"

# 轮转：仅保留最近 KEEP 份，删除更早的
ls -1t "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
