#!/bin/bash
# 商品检查和修正系统 - 云服务器一键部署脚本
# 参考数据库迁移脚本的部署方式
# 用法: ./deploy_to_cloud.sh [--rebuild] [--docker-only] [--check]
#   --rebuild / -r  强制重新构建镜像并重新安装依赖（默认使用缓存，不重复下载依赖）
#   --docker-only   仅 SSH 到服务器执行 Docker 配置加固（daemon.json + restart + prune），不打包不部署
#   --check         仅 SSH 到服务器做一次状态检查（容器、健康、磁盘、daemon 配置）并输出结果

set -e  # 遇到错误立即退出

# 是否强制重建（重新下载依赖）
REBUILD=""
# 是否仅执行 Docker 配置加固
DOCKER_ONLY=""
# 是否仅做服务器状态检查
CHECK_ONLY=""
for arg in "$@"; do
    case "$arg" in
        --rebuild|-r) REBUILD="--no-cache"; break ;;
        --docker-only) DOCKER_ONLY=1; break ;;
        --check) CHECK_ONLY=1; break ;;
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

# --docker-only: 仅 SSH 执行 Docker 配置加固（daemon + prune）
if [ -n "$DOCKER_ONLY" ]; then
    echo "仅执行 Docker 配置加固（daemon.json + restart + prune）..."
    ssh -i "${SSH_KEY/#\~/$HOME}" ${CLOUD_USER}@${CLOUD_HOST} << 'REMOTE'
set -e
echo "Docker 配置加固..."
if [ -w /etc/docker/daemon.json ] 2>/dev/null || { [ ! -f /etc/docker/daemon.json ] && [ -w /etc/docker ]; }; then
  python3 << 'PYEND'
import json
p = "/etc/docker/daemon.json"
try:
    with open(p) as f:
        d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    d = {}
d.update({
    "log-driver": "json-file",
    "log-opts": {"max-size": "50m", "max-file": "3"},
    "live-restore": True
})
with open(p, "w") as f:
    json.dump(d, f, indent=2)
PYEND
  echo "  已写入 /etc/docker/daemon.json"
  systemctl restart docker
  sleep 5
  echo "  Docker 已重启"
else
  echo "  跳过 daemon.json（无写权限）"
fi
docker image prune -f
docker builder prune -f
docker system prune -f
echo "  清理完成"
REMOTE
    echo "✓ Docker 配置加固完成"
    exit 0
fi

# 步骤0: 本地 Python 语法检查（避免有语法错误的代码被部署）
echo "[0/6] 本地代码检查（Python 语法）..."
FAILED=""
for f in backend/*.py; do
    if [ -f "$f" ] && ! python3 -m py_compile "$f" 2>/dev/null; then
        echo "❌ 语法错误: $f"
        python3 -m py_compile "$f" 2>&1 || true
        FAILED=1
    fi
done
if [ -n "$FAILED" ]; then
    echo "❌ 存在语法错误，已中止部署。请修复后再运行。"
    exit 1
fi
echo "✓ 语法检查通过"
echo ""

# 步骤1: 打包项目（含 OCRPlus，compose 内用容器名通信）
echo "[1/6] 打包项目（goods_review_web + OCRPlus）..."
TAR_FILE="goods_review_web_$(date +%Y%m%d_%H%M%S).tar.gz"
# 从 goods_review_web 的上一级打包，保证服务器上有 /opt/goods_review_web 和 /opt/OCRPlus
ROOT_DIR="$(cd .. && pwd)"
cd "$ROOT_DIR"
# 排除本机敏感/本地配置；OCRPlus 排除 .git、venv、训练数据、大模型、安装包、临时样本
tar --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='goods_review_web/backend/.env' \
    --exclude='goods_review_web/docker/.env' \
    --exclude='OCRPlus/easyocr_models' \
    --exclude='OCRPlus/venv' \
    --exclude='OCRPlus/training_data' \
    --exclude='OCRPlus/Miniconda3*' \
    --exclude='OCRPlus/temp_*' \
    --exclude='OCRPlus/predictions_*.json' \
    --exclude='OCRPlus/temp_sample_set.json' \
    -czf "$TAR_FILE" goods_review_web/ OCRPlus/

if [ $? -ne 0 ]; then
    echo "❌ 打包失败"
    exit 1
fi

echo "✓ 打包完成: $TAR_FILE"
echo ""

# 步骤2: 上传到云服务器
echo "[2/6] 上传到云服务器..."
scp -i "${SSH_KEY/#\~/$HOME}" "$TAR_FILE" ${CLOUD_USER}@${CLOUD_HOST}:/tmp/

if [ $? -ne 0 ]; then
    echo "❌ 上传失败"
    exit 1
fi

echo "✓ 上传完成"
echo ""

# 步骤3: 在云服务器上解压和部署
echo "[3/6] 在云服务器上部署..."
ssh -i "${SSH_KEY/#\~/$HOME}" ${CLOUD_USER}@${CLOUD_HOST} << EOF
set -e

echo "创建部署目录..."
mkdir -p /opt
cd /opt

echo "解压文件（得到 goods_review_web 与 OCRPlus）..."
tar -xzf /tmp/$TAR_FILE

echo "进入 docker 目录..."
cd ${CLOUD_DIR}/docker

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

# OCRPlus 在 compose 内用容器名，无需改
# OCRPLUS_BASE_URL=http://ocrplus:5002
ENVEOF
    echo "✓ 已创建环境变量文件（请编辑 .env 填写 BIGMODEL_API_KEY 后重启服务）"
else
    echo "✓ 环境变量文件已存在"
fi
if [ -f .env ] && ! grep -q 'PREVIEW_LAB_URL' .env 2>/dev/null; then
  echo "" >> .env
  echo "# 预审 Lab 反馈（保存/废弃时通知）" >> .env
  echo "PREVIEW_LAB_URL=http://preview_lab:5003" >> .env
  echo "  已在 .env 中追加 PREVIEW_LAB_URL=http://preview_lab:5003"
fi

echo "停止旧容器（如果存在）..."
docker-compose down || true
docker rm -f goods_review_frontend goods_review_backend ocrplus 2>/dev/null || true

echo "释放宿主机上占用 5002 的进程（如旧 OCRPlus）..."
for pid in \$(lsof -i :5002 -t 2>/dev/null); do
  [ -z "\$pid" ] && continue
  kill -TERM "\$pid" 2>/dev/null && echo "  已向进程 \$pid 发送 SIGTERM" || true
done
sleep 2
for pid in \$(lsof -i :5002 -t 2>/dev/null); do
  [ -z "\$pid" ] && continue
  kill -9 "\$pid" 2>/dev/null && echo "  已强制结束进程 \$pid" || true
done

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

echo "检查服务（通过 Nginx 8080 统一入口）..."
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/health | grep -q 200; then
        echo "✓ 后端 API 运行正常 (8080/api/health)"
        break
    fi
    if [ "\$i" -eq 10 ]; then
        echo "⚠️  后端未响应，请检查: cd ${CLOUD_DIR}/docker && docker-compose logs backend"
    fi
    sleep 2
done
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q 200; then
    echo "✓ 前端页面可访问 (8080)"
else
    echo "⚠️  前端可能未正常启动"
fi

echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo ""
echo "📌 访问地址（API 与前端均通过 8080）:"
echo "   页面与 API: http://${CLOUD_HOST}:8080   (API 路径: /api/...)"
echo ""

echo "Docker 配置加固（daemon 日志限制 + live-restore + 清理）..."
if [ -w /etc/docker/daemon.json ] 2>/dev/null || { [ ! -f /etc/docker/daemon.json ] && [ -w /etc/docker ]; }; then
  python3 << 'PYEND'
import json
p = "/etc/docker/daemon.json"
try:
    with open(p) as f:
        d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    d = {}
d.update({
    "log-driver": "json-file",
    "log-opts": {"max-size": "50m", "max-file": "3"},
    "live-restore": True
})
with open(p, "w") as f:
    json.dump(d, f, indent=2)
PYEND
  echo "  已写入 /etc/docker/daemon.json"
  systemctl restart docker
  sleep 5
  echo "  Docker 已重启（live-restore 保持容器）"
else
  echo "  跳过 daemon.json（无写权限，请 root 手动配置）"
fi
docker image prune -f
docker builder prune -f
docker system prune -f
echo "  清理未使用镜像与构建缓存完成"

echo ""
EOF

if [ $? -ne 0 ]; then
    echo "❌ 部署失败"
    exit 1
fi

# 步骤4: 清理本地临时文件
echo ""
echo "[4/6] 清理临时文件..."
rm -f "$TAR_FILE"
echo "✓ 清理完成"
echo ""

# 步骤5: 显示访问信息
echo "[5/6] 部署完成！"
echo ""
echo "=========================================="
echo "  ✅ 部署成功！"
echo "=========================================="
echo ""
echo "📌 访问地址（仅开放 8080）:"
echo "   页面与 API: http://${CLOUD_HOST}:8080"
echo ""
echo "📋 常用命令:"
echo "   SSH登录: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST}"
echo "   查看日志: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose logs -f backend'"
echo "   重启服务: ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose restart'"
echo ""
echo "🔍 若 502，先看后端日志与 DB 配置:"
echo "   ssh -i ${SSH_KEY} ${CLOUD_USER}@${CLOUD_HOST} 'cd ${CLOUD_DIR}/docker && docker-compose logs --tail 80 backend && cat .env | grep -E \"^DB_\"'"
echo "   云服务器防火墙/安全组需开放 8080"
echo ""
