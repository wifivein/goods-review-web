#!/bin/bash

# 商品检查和修正系统启动脚本

echo "=========================================="
echo "  商品检查和修正系统"
echo "=========================================="

# 检查是否在项目根目录
if [ ! -f "backend/app.py" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python"
    exit 1
fi

# 检查是否安装了依赖
if [ ! -d "backend/venv" ] && [ ! -d "backend/env" ]; then
    echo "正在创建虚拟环境..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# 启动后端
echo "正在启动后端服务..."
cd backend
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "env" ]; then
    source env/bin/activate
fi

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "警告: 未找到.env文件，使用默认配置"
    echo "建议创建.env文件并配置数据库连接信息"
fi

echo "后端服务启动在 http://localhost:5000"
python app.py &
BACKEND_PID=$!

cd ..

# 等待后端启动
sleep 2

# 启动前端（使用Python简单HTTP服务器）
echo "正在启动前端服务..."
cd frontend

# 检查端口是否被占用
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo "警告: 端口8080已被占用，请手动启动前端服务"
    echo "或者访问: http://localhost:8080"
else
    echo "前端服务启动在 http://localhost:8080"
    python3 -m http.server 8080 &
    FRONTEND_PID=$!
fi

cd ..

echo ""
echo "=========================================="
echo "  服务已启动！"
echo "  前端: http://localhost:8080"
echo "  后端: http://localhost:5000"
echo ""
echo "  按 Ctrl+C 停止服务"
echo "=========================================="

# 等待用户中断
trap "echo ''; echo '正在停止服务...'; kill $BACKEND_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; exit" INT

wait
