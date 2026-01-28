#!/bin/bash
# 检查服务状态的诊断脚本

echo "=========================================="
echo "  服务状态诊断"
echo "=========================================="
echo ""

# 检查 Docker 容器状态
echo "[1] 检查 Docker 容器状态..."
cd "$(dirname "$0")"
if docker-compose ps | grep -q "goods_review_backend"; then
    echo "✓ 后端容器存在"
    docker-compose ps
else
    echo "✗ 后端容器不存在或未运行"
    echo ""
    echo "尝试启动服务..."
    docker-compose up -d
    sleep 5
    docker-compose ps
fi
echo ""

# 检查端口监听
echo "[2] 检查端口 5001 是否在监听..."
if lsof -i :5001 > /dev/null 2>&1 || ss -tlnp | grep -q ":5001"; then
    echo "✓ 端口 5001 正在监听"
    lsof -i :5001 || ss -tlnp | grep ":5001"
else
    echo "✗ 端口 5001 未在监听"
fi
echo ""

# 检查容器日志
echo "[3] 检查后端容器日志（最近 20 行）..."
docker-compose logs --tail=20 backend
echo ""

# 测试 API 连接
echo "[4] 测试 API 连接..."
if curl -s -m 5 http://localhost:5001/api/health > /dev/null 2>&1; then
    echo "✓ API 健康检查通过"
    curl -s http://localhost:5001/api/health
else
    echo "✗ API 健康检查失败"
    echo "尝试测试 save-tab-mapping 接口..."
    curl -v -X POST http://localhost:5001/api/design/save-tab-mapping \
        -H "Content-Type: application/json" \
        -d '{"test": "connection"}' \
        --connect-timeout 5 \
        --max-time 10 || echo "连接失败"
fi
echo ""

# 检查防火墙
echo "[5] 检查防火墙状态..."
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --list-ports 2>/dev/null | grep -q "5001" && echo "✓ 防火墙已开放 5001 端口" || echo "⚠️  防火墙可能未开放 5001 端口"
elif command -v ufw &> /dev/null; then
    ufw status | grep -q "5001" && echo "✓ 防火墙已开放 5001 端口" || echo "⚠️  防火墙可能未开放 5001 端口"
else
    echo "⚠️  未检测到防火墙工具，请手动检查"
fi
echo ""

echo "=========================================="
echo "  诊断完成"
echo "=========================================="
