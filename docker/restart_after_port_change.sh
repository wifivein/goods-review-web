#!/bin/bash
# 重启服务脚本（移除5001端口后）

echo "=========================================="
echo "  重启 goods_review_web 服务"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# 停止服务
echo "[1] 停止现有服务..."
docker-compose down
echo "✓ 服务已停止"
echo ""

# 启动服务
echo "[2] 启动服务..."
docker-compose up -d
echo "✓ 服务启动中..."
echo ""

# 等待服务启动
echo "[3] 等待服务启动（最多 30 秒）..."
for i in {1..15}; do
    if curl -s -m 2 http://localhost:8080/api/health > /dev/null 2>&1; then
        echo "✓ 服务已成功启动！"
        echo ""
        echo "测试接口..."
        curl -s http://localhost:8080/api/health | head -20
        echo ""
        echo ""
        echo "=========================================="
        echo "  ✅ 服务重启成功！"
        echo "=========================================="
        echo ""
        echo "📌 重要提示："
        echo "   - 5001 端口已移除，不再可用"
        echo "   - 所有请求现在统一通过 8080 端口访问"
        echo "   - n8n 工作流需要修改为: http://localhost:8080/api/..."
        echo ""
        exit 0
    fi
    echo "  等待中... ($i/15)"
    sleep 2
done

echo ""
echo "⚠️  服务可能未完全启动，请检查日志："
echo "   docker-compose logs backend"
echo ""
