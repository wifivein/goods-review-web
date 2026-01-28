#!/bin/bash
# 重启服务脚本

echo "=========================================="
echo "  重启后端服务"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# 停止服务
echo "[1] 停止现有服务..."
docker-compose stop backend
docker-compose rm -f backend 2>/dev/null || true
echo "✓ 服务已停止"
echo ""

# 启动服务
echo "[2] 启动服务..."
docker-compose up -d backend
echo "✓ 服务启动中..."
echo ""

# 等待服务启动
echo "[3] 等待服务启动（最多 30 秒）..."
for i in {1..15}; do
    if curl -s -m 2 http://localhost:5001/api/health > /dev/null 2>&1; then
        echo "✓ 服务已成功启动！"
        echo ""
        echo "测试 save-tab-mapping 接口..."
        curl -X POST http://localhost:5001/api/design/save-tab-mapping \
            -H "Content-Type: application/json" \
            -d '{"tab_id": 999999, "product_id": "test", "test": true}' \
            --connect-timeout 5 \
            --max-time 10
        echo ""
        echo ""
        echo "=========================================="
        echo "  ✅ 服务重启成功！"
        echo "=========================================="
        exit 0
    fi
    echo "  等待中... ($i/15)"
    sleep 2
done

echo ""
echo "⚠️  服务可能未完全启动，请检查日志："
echo "   docker-compose logs backend"
echo ""
