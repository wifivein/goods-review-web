#!/bin/bash
# 商品检查和修正系统 - 云服务器一键部署脚本
# 参考数据库迁移脚本的部署方式
# 用法: ./deploy_to_cloud.sh [--rebuild]
#   --rebuild / -r  强制重新构建镜像并重新安装依赖（默认使用缓存，不重复下载依赖）

set -e  # 遇到错误立即退出

# 是否强制重建（重新下载依赖）
REBUILD=""
for arg in "$@"; do
    case "$arg" in
        --rebuild|-r) REBUILD="--no-cache"; break ;;
    esac
done

# 云服务器配置（参考 migrate_database_to_cloud.sh）
CLOUD_HOST="101.33.241.82"
SSH_KEY="~/.ssh/id_rsa_ocrplus"
CLOUD_USER="root"
CLOUD_DIR="/opt/goods_review_web"

echo "=========================================="
echo "  商品检查和修正系统 - 云服务器部署"
echo "=========================================="
echo ""

# 检查是否在项目根目录
if [ ! -f "backend/app.py" ]; then
    echo "❌ 错误: 请在 goods_review_web 目录下运行此脚本"
    exit 1
fi

# 检查SSH密钥
if [ ! -f "${SSH_KEY/#\~/$HOME}" ]; then
    echo "⚠️  警告: SSH密钥不存在: ${SSH_KEY}"
    echo "   请确保已配置SSH密钥或修改脚本中的SSH_KEY变量"
    read -p "是否继续？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✓ 环境检查通过"
echo ""

# 步骤1: 打包项目
echo "[1/5] 打包项目..."
TAR_FILE="goods_review_web_$(date +%Y%m%d_%H%M%S).tar.gz"
cd ..
# 排除本机敏感/本地配置，避免覆盖服务器上的 docker/.env（服务器用脚本默认或已有配置）
tar --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='goods_review_web/backend/.env' \
    --exclude='goods_review_web/docker/.env' \
    -czf "$TAR_FILE" goods_review_web/

if [ $? -ne 0 ]; then
    echo "❌ 打包失败"
    exit 1
fi

echo "✓ 打包完成: $TAR_FILE"
echo ""

# 步骤2: 上传到云服务器
echo "[2/5] 上传到云服务器..."
scp -i "${SSH_KEY/#\~/$HOME}" "$TAR_FILE" ${CLOUD_USER}@${CLOUD_HOST}:/tmp/

if [ $? -ne 0 ]; then
    echo "❌ 上传失败"
    exit 1
fi

echo "✓ 上传完成"
echo ""

# 步骤3: 在云服务器上解压和部署
echo "[3/5] 在云服务器上部署..."
ssh -i "${SSH_KEY/#\~/$HOME}" ${CLOUD_USER}@${CLOUD_HOST} << EOF
set -e

echo "创建部署目录..."
mkdir -p ${CLOUD_DIR}
cd ${CLOUD_DIR}

echo "解压文件..."
tar -xzf /tmp/$TAR_FILE -C ${CLOUD_DIR} --strip-components=1

echo "进入docker目录..."
cd docker

echo "创建环境变量文件（如果不存在）..."
if [ ! -f .env ]; then
    cat > .env << ENVEOF
# 数据库配置
DB_HOST=101.33.241.82
DB_PORT=3307
DB_USER=root
DB_PASSWORD=root
DB_NAME=temu_baodan

# 外部API配置
SAVE_API_URL=http://temebaodan.all369.cn/api/pc/savegoods
AUTH_TOKEN=d6439e3f68072e610aedb646f0589717cb54061d4b336b94fbe73be79886a24d

# 智谱 GLM-4V 图片理解（/api/vision/describe 必填）
BIGMODEL_API_KEY=
ENVEOF
    echo "✓ 已创建环境变量文件（请编辑 .env 填写 BIGMODEL_API_KEY 后重启服务）"
else
    echo "✓ 环境变量文件已存在"
fi

echo "停止旧容器（如果存在）..."
docker-compose down || true
docker rm -f goods_review_frontend goods_review_backend 2>/dev/null || true

echo "构建并启动服务..."
if [ -n "$REBUILD" ]; then
    echo "  (使用 --rebuild，将重新安装依赖)"
    docker-compose build $REBUILD
else
    echo "  (使用缓存，依赖未变更时不会重新下载；需重装依赖请加 --rebuild)"
    docker-compose build
fi
docker-compose up -d

echo "等待服务启动..."
sleep 5

echo "检查服务状态..."
docker-compose ps

echo "检查后端健康状态..."
for i in {1..10}; do
    if curl -s http://localhost:5001/api/health > /dev/null 2>&1; then
        echo "✓ 后端服务运行正常"
        break
    fi
    sleep 2
done

echo "检查前端服务..."
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "✓ 前端服务运行正常"
else
    echo "⚠️  前端服务可能未正常启动"
fi

echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo ""
echo "📌 访问地址:"
echo "   前端: http://${CLOUD_HOST}:8080"
echo "   后端API: http://${CLOUD_HOST}:5001/api"
echo ""
EOF

if [ $? -ne 0 ]; then
    echo "❌ 部署失败"
    exit 1
fi

# 步骤4: 清理本地临时文件
echo ""
echo "[4/5] 清理临时文件..."
rm -f "$TAR_FILE"
echo "✓ 清理完成"
echo ""

# 步骤5: 显示访问信息
echo "[5/5] 部署完成！"
echo ""
echo "=========================================="
echo "  ✅ 部署成功！"
echo "=========================================="
echo ""
echo "📌 访问地址:"
echo "   前端: http://${CLOUD_HOST}:8080"
echo "   后端API: http://${CLOUD_HOST}:5001/api/health"
echo ""
echo "📋 常用命令:"
echo "   SSH登录: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST}"
echo "   查看日志: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose logs -f'"
echo "   重启服务: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose restart'"
echo ""
echo "🔍 如果无法访问，请检查:"
echo "   1. 云服务器防火墙是否开放 8080 和 5001 端口"
echo "   2. 安全组规则是否允许访问"
echo "   3. 查看服务日志: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose logs'"
echo ""
