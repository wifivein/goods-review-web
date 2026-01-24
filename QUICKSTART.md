# 快速开始指南

## 方式一：使用Docker（推荐，最简单）

### 1. 进入docker目录
```bash
cd goods_review_web/docker
```

### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，修改数据库配置
```

### 3. 启动服务
```bash
docker-compose up -d
```

### 4. 访问系统
- 前端: http://localhost:8080
- 后端API: http://localhost:5000/api/health

### 5. 停止服务
```bash
docker-compose down
```

## 方式二：本地开发（不使用Docker）

### 1. 启动后端

```bash
cd goods_review_web/backend

# 安装依赖
pip install -r requirements.txt

# （可选）创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 启动服务
python app.py
```

后端将在 http://localhost:5000 启动

### 2. 启动前端

#### 选项A：使用Python HTTP服务器（推荐）

```bash
cd goods_review_web/frontend
python3 -m http.server 8080
```

#### 选项B：使用Node.js

```bash
cd goods_review_web/frontend
npx http-server -p 8080
```

#### 选项C：直接打开（不推荐，可能有跨域问题）

直接用浏览器打开 `frontend/index.html`，但需要修改 `app.js` 中的 `API_BASE_URL`。

### 3. 访问系统

打开浏览器访问: http://localhost:8080

## 方式三：使用启动脚本（Linux/Mac）

```bash
cd goods_review_web
./start.sh
```

脚本会自动启动后端和前端服务。

## 配置说明

### 数据库配置

如果使用Docker，在 `docker/.env` 中配置：
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=temu_baodan
```

如果本地开发，在 `backend/.env` 中配置（或直接修改 `app.py` 中的默认值）。

### 前端API地址配置

如果前端和后端不在同一域名，需要修改 `frontend/app.js` 中的 `API_BASE_URL`：

```javascript
const API_BASE_URL = 'http://localhost:5000/api';
```

## 常见问题

### 1. 数据库连接失败

- 检查MySQL服务是否运行
- 检查数据库配置是否正确
- 检查数据库和表是否存在

### 2. 前端无法连接后端

- 检查后端是否正常启动（访问 http://localhost:5000/api/health）
- 检查浏览器控制台是否有错误
- 如果使用直接打开HTML文件，需要修改 `API_BASE_URL` 或使用HTTP服务器

### 3. 图片无法显示

- 检查图片URL是否可访问
- 检查网络连接
- 图片加载失败会显示占位图

### 4. 保存接口调用失败

- 检查 `SAVE_API_URL` 配置是否正确
- 检查网络连接
- 如果接口需要认证，需要在 `backend/app.py` 中添加认证信息

## 下一步

1. 确认数据库连接正常
2. 测试商品列表加载
3. 测试商品编辑功能
4. 测试保存功能
5. 如果保存接口需要认证，添加认证信息
