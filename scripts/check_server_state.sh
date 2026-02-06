#!/bin/bash
# 服务器状态与表检查：容器、健康接口、环境变量、关键表数据量
# 在 goods_review_web 目录下执行: ./scripts/check_server_state.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

DEPLOY_SH="./deploy_to_cloud.sh"
[ ! -f "$DEPLOY_SH" ] && DEPLOY_SH="$(cd "$ROOT_DIR/.." && pwd)/goods_review_web/deploy_to_cloud.sh"
[ ! -f "$DEPLOY_SH" ] && { echo "未找到 deploy_to_cloud.sh"; exit 1; }

CLOUD_HOST="101.33.241.82"
CLOUD_USER="root"
SSH_KEY="$HOME/.ssh/id_rsa_ocrplus"
CLOUD_DIR="/opt/goods_review_web"
while IFS= read -r line; do
  [[ "$line" =~ ^CLOUD_HOST=\"(.*)\" ]] && CLOUD_HOST="${BASH_REMATCH[1]}"
  [[ "$line" =~ ^CLOUD_USER=\"(.*)\" ]] && CLOUD_USER="${BASH_REMATCH[1]}"
  [[ "$line" =~ ^SSH_KEY=\"(.*)\" ]] && SSH_KEY="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$line" =~ ^CLOUD_DIR=\"(.*)\" ]] && CLOUD_DIR="${BASH_REMATCH[1]}"
done < "$DEPLOY_SH"

[ -f "docker/.env" ] && source docker/.env 2>/dev/null || true
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-root}"

echo "=========================================="
echo "  服务器状态检查  ${CLOUD_USER}@${CLOUD_HOST}"
echo "=========================================="
echo ""

ssh -i "$SSH_KEY" -o ConnectTimeout=15 "${CLOUD_USER}@${CLOUD_HOST}" bash -s << REMOTE
set -e
echo "--- 1. Docker 容器 ---"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -20

echo ""
echo "--- 2. Compose 服务 (${CLOUD_DIR}/docker) ---"
cd ${CLOUD_DIR}/docker 2>/dev/null && docker compose ps 2>/dev/null || docker-compose ps 2>/dev/null || echo "未找到 compose 或未在目录"

echo ""
echo "--- 3. 健康与接口 ---"
curl -s -o /dev/null -w "  8080 (Nginx/后端): %{http_code}\n" http://localhost:8080/api/health 2>/dev/null || echo "  8080: 请求失败"
curl -s -o /dev/null -w "  5003 (preview-lab): %{http_code}\n" http://localhost:5003/api/health 2>/dev/null || echo "  5003: 请求失败"

echo ""
echo "--- 4. 环境变量 (docker/.env) ---"
if [ -f ${CLOUD_DIR}/docker/.env ]; then
  grep -E "^(PREVIEW_LAB_URL|DB_HOST|DB_PORT|DB_NAME|DB_NAME_LAB)=" ${CLOUD_DIR}/docker/.env 2>/dev/null || true
else
  echo "  未找到 .env"
fi

echo ""
echo "--- 5. 数据库表（MySQL 容器内执行）---"
MYSQL_CONTAINER=\$(docker ps --format '{{.Names}}' | grep -iE 'mysql|mariadb' | head -1)
if [ -z "\$MYSQL_CONTAINER" ]; then
  echo "  未检测到 MySQL 容器，跳过表检查"
else
  echo "  使用容器: \$MYSQL_CONTAINER"
  docker exec "\$MYSQL_CONTAINER" mysql -u"${DB_USER}" -p"${DB_PASSWORD}" -e "
    SELECT 'temu_baodan.negative_reason_log' AS tbl, COUNT(*) AS cnt FROM temu_baodan.negative_reason_log
    UNION ALL
    SELECT 'temu_baodan.label_badcase', COUNT(*) FROM temu_baodan.label_badcase
    UNION ALL
    SELECT 'temu_baodan_lab.audit_feedback', COUNT(*) FROM temu_baodan_lab.audit_feedback;
  " 2>/dev/null || echo "  表查询失败（检查库名与权限）"

  echo ""
  echo "  negative_reason_log 按维度统计:"
  docker exec "\$MYSQL_CONTAINER" mysql -u"${DB_USER}" -p"${DB_PASSWORD}" -e "
    SELECT dimension, COUNT(*) AS cnt FROM temu_baodan.negative_reason_log GROUP BY dimension;
  " 2>/dev/null || true

  echo ""
  echo "  negative_reason_log 最近 5 条:"
  docker exec "\$MYSQL_CONTAINER" mysql -u"${DB_USER}" -p"${DB_PASSWORD}" -e "
    SELECT id, dimension, LEFT(reason,40) AS reason_preview, created_at FROM temu_baodan.negative_reason_log ORDER BY id DESC LIMIT 5;
  " 2>/dev/null || true
fi

echo ""
echo "--- 6. preview-lab 最近反馈条数 ---"
curl -s "http://localhost:5003/api/feedback/list?limit=3" 2>/dev/null | head -c 400
echo ""
REMOTE

echo ""
echo "=========================================="
echo "  检查结束"
echo "=========================================="
