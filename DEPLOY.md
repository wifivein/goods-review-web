# 商品检查和修正系统 - 云服务器部署指南

## 📋 前置要求

1. **云服务器**（已购买并配置好）
2. **Docker** 和 **Docker Compose** 已安装
3. **数据库已迁移到云服务器**（地址：`101.33.241.82:3307`）

## 🚀 部署步骤

### 1. 上传代码到云服务器

```bash
# 在本地打包项目
cd goods_review_web
tar -czf goods_review_web.tar.gz .

# 上传到云服务器（使用 scp 或 sftp）
scp goods_review_web.tar.gz user@your-server-ip:/path/to/deploy/

# 在云服务器上解压
ssh user@your-server-ip
cd /path/to/deploy
tar -xzf goods_review_web.tar.gz
cd goods_review_web
```

### 2. 配置环境变量

创建 `.env` 文件（在 `docker/` 目录下，或项目根目录）：

```bash
cd docker
cat > .env << EOF
# 数据库配置
DB_HOST=101.33.241.82
DB_PORT=3307
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=temu_baodan

# 外部API配置
SAVE_API_URL=http://temebaodan.all369.cn/api/pc/savegoods
AUTH_TOKEN=your_auth_token_here
EOF
```

**重要：** 请将 `your_password_here` 和 `your_auth_token_here` 替换为实际值。

### 3. 启动服务

```bash
cd docker
docker-compose up -d
```

### 4. 检查服务状态

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 检查后端健康状态
curl http://localhost:5001/api/health
```

### 5. 访问服务

- **前端地址**：`http://your-server-ip:8080`
- **后端API**：`http://your-server-ip:5001/api`

## 🔧 配置说明

### 端口配置

- **前端（Nginx）**：`8080` → 容器内 `80`
- **后端（Flask）**：`5001` → 容器内 `5000`

如需修改端口，编辑 `docker-compose.yml` 中的 `ports` 配置。

### 数据库配置

数据库配置已更新为云服务器地址：
- **Host**: `101.33.241.82`
- **Port**: `3307`

如需修改，可通过环境变量或直接修改 `backend/app.py` 中的默认值。

### 前端API地址

前端会自动检测部署环境：
- **本地开发**（localhost）：使用 `http://localhost:5001/api`
- **云服务器部署**：使用相对路径 `/api`（通过 nginx 反向代理）

## 📝 常用命令

### 启动服务
```bash
docker-compose up -d
```

### 停止服务
```bash
docker-compose down
```

### 重启服务
```bash
docker-compose restart
```

### 查看日志
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看后端日志
docker-compose logs -f backend

# 查看前端日志
docker-compose logs -f frontend
```

### 更新代码
```bash
# 1. 停止服务
docker-compose down

# 2. 更新代码文件

# 3. 重新构建并启动
docker-compose up -d --build
```

## 🔍 故障排查

### 1. 数据库连接失败

**检查项：**
- 数据库地址和端口是否正确
- 数据库用户名和密码是否正确
- 云服务器防火墙是否开放了数据库端口（3307）
- 数据库是否允许远程连接

**测试连接：**
```bash
# 在云服务器上测试数据库连接
docker-compose exec backend python -c "
import pymysql
conn = pymysql.connect(
    host='101.33.241.82',
    port=3307,
    user='root',
    password='your_password',
    database='temu_baodan'
)
print('数据库连接成功！')
conn.close()
"
```

### 2. 前端无法访问后端API

**检查项：**
- nginx 配置是否正确
- 后端服务是否正常运行
- 网络连接是否正常

**测试：**
```bash
# 测试后端健康检查
curl http://localhost:5001/api/health

# 测试 nginx 反向代理
curl http://localhost:8080/api/health
```

### 3. 外部API调用失败

**检查项：**
- `SAVE_API_URL` 是否正确
- `AUTH_TOKEN` 是否正确
- 云服务器是否能访问外部网络

**测试：**
```bash
# 测试外部API连接
curl -X POST http://temebaodan.all369.cn/api/pc/savegoods \
  -H "Authorization: your_auth_token" \
  -H "Content-Type: application/x-www-form-urlencoded"
```

## 🔐 安全建议

1. **修改默认端口**：如果可能，将 `8080` 和 `5001` 改为其他端口
2. **使用 HTTPS**：生产环境建议配置 SSL 证书，使用 HTTPS
3. **防火墙配置**：只开放必要的端口
4. **数据库安全**：使用强密码，限制数据库访问IP
5. **环境变量**：敏感信息（密码、Token）使用环境变量，不要硬编码

## 📞 支持

如遇到问题，请检查：
1. Docker 容器日志：`docker-compose logs`
2. 后端日志：查看 `backend/app.py` 中的 `print` 输出
3. 浏览器控制台：查看前端错误信息
