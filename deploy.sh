#!/bin/bash

# 商品检查和修正系统 - 一键部署脚本
# 使用方法: ./deploy.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  商品检查和修正系统 - 云服务器部署"
echo "=========================================="
echo ""

# 检查是否在项目根目录
if [ ! -f "backend/app.py" ]; then
    echo "❌ 错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 未找到 Docker，请先安装 Docker"
    echo "   安装命令: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# 检查 Docker Compose 是否安装
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ 错误: 未找到 Docker Compose，请先安装"
    echo "   安装命令: sudo apt-get install docker-compose-plugin"
    exit 1
fi

echo "✓ Docker 环境检查通过"
echo ""

# 检查环境变量文件
ENV_FILE="docker/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  未找到环境变量文件，正在创建..."
    cat > "$ENV_FILE" << EOF
# 数据库配置
DB_HOST=101.33.241.82
DB_PORT=3307
DB_USER=root
DB_PASSWORD=请修改为实际密码
DB_NAME=temu_baodan

# 外部API配置
SAVE_API_URL=http://temebaodan.all369.cn/api/pc/savegoods
AUTH_TOKEN=请修改为实际Token
EOF
    echo "✓ 已创建环境变量文件: $ENV_FILE"
    echo "⚠️  请编辑 $ENV_FILE 文件，填入正确的数据库密码和 AUTH_TOKEN"
    echo ""
    read -p "按 Enter 继续（确保已修改环境变量）..."
fi

# 检查必要的环境变量
source "$ENV_FILE" 2>/dev/null || true
if [ "$DB_PASSWORD" = "请修改为实际密码" ] || [ -z "$DB_PASSWORD" ]; then
    echo "❌ 错误: 请在 $ENV_FILE 中设置正确的 DB_PASSWORD"
    exit 1
fi

echo "✓ 环境变量检查通过"
echo ""

# 进入 docker 目录
cd docker

# 停止旧容器（如果存在）
echo "正在停止旧容器..."
docker-compose down 2>/dev/null || true

# 构建并启动服务
echo "正在构建 Docker 镜像..."
docker-compose build --no-cache

echo "正在启动服务..."
docker-compose up -d

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "=========================================="
echo "  服务状态检查"
echo "=========================================="
docker-compose ps

# 检查后端健康状态
echo ""
echo "检查后端健康状态..."
for i in {1..10}; do
    if curl -s http://localhost:5001/api/health > /dev/null 2>&1; then
        echo "✓ 后端服务运行正常"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠️  后端服务可能未正常启动，请检查日志: docker-compose logs backend"
    fi
    sleep 2
done

# 检查前端
echo "检查前端服务..."
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "✓ 前端服务运行正常"
else
    echo "⚠️  前端服务可能未正常启动，请检查日志: docker-compose logs frontend"
fi

# 获取服务器IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "your-server-ip")

echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo ""
echo "📌 访问地址:"
echo "   前端: http://${SERVER_IP}:8080"
echo "   后端API: http://${SERVER_IP}:5001/api"
echo ""
echo "📋 常用命令:"
echo "   查看日志: cd docker && docker-compose logs -f"
echo "   停止服务: cd docker && docker-compose down"
echo "   重启服务: cd docker && docker-compose restart"
echo ""
echo "🔍 如果无法访问，请检查:"
echo "   1. 云服务器防火墙是否开放 8080 和 5001 端口"
echo "   2. 安全组规则是否允许访问"
echo "   3. 查看服务日志: docker-compose logs"
echo ""
