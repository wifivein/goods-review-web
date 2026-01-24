# 商品检查和修正系统

用于商品自动整理之后的人工检查和修正的Web系统。

## 功能特性

- ✅ 商品列表展示（支持分页、搜索、筛选）
- ✅ 商品详情查看（主图、第三张轮播图、标题）
- ✅ 商品编辑（修改主图、轮播图顺序、标题）
- ✅ 图片预览和管理
- ✅ 批量保存功能
- ✅ 响应式设计，现代化UI

## 技术栈

- **后端**: Python Flask + PyMySQL
- **前端**: Vue 3 + Element Plus
- **数据库**: MySQL
- **部署**: Docker + Docker Compose

## 快速开始

### 方式一：Docker部署（推荐）

1. **配置环境变量**

```bash
cd docker
cp .env.example .env
# 编辑 .env 文件，修改数据库配置和API地址
```

2. **启动服务**

```bash
docker-compose up -d
```

3. **访问系统**

- 前端: http://localhost:8080
- 后端API: http://localhost:5000

### 方式二：本地开发

#### 后端启动

```bash
cd backend
pip install -r requirements.txt

# 创建 .env 文件（可选，也可以直接修改代码中的配置）
cp .env.example .env
# 编辑 .env 文件

# 启动服务
python app.py
```

#### 前端启动

前端使用静态文件，可以直接用浏览器打开 `frontend/index.html`，或者使用简单的HTTP服务器：

```bash
cd frontend

# 使用Python
python -m http.server 8080

# 或使用Node.js
npx http-server -p 8080
```

然后访问 http://localhost:8080

**注意**: 如果前端和后端不在同一域名，需要修改 `frontend/app.js` 中的 `API_BASE_URL`。

## 项目结构

```
goods_review_web/
├── backend/              # Flask后端
│   ├── app.py           # 主应用文件
│   ├── requirements.txt # Python依赖
│   └── .env.example     # 环境变量示例
├── frontend/            # Vue前端
│   ├── index.html      # 主页面
│   └── app.js          # Vue应用逻辑
├── docker/             # Docker配置
│   ├── Dockerfile.backend
│   ├── docker-compose.yml
│   └── .env.example
└── README.md           # 本文件
```

## API接口说明

### 1. 健康检查
```
GET /api/health
```

### 2. 获取商品列表
```
GET /api/goods/list
参数:
  - page: 页码（默认1）
  - page_size: 每页数量（默认20）
  - search: 搜索关键词（可选）
  - user_id: 用户ID（可选）
```

### 3. 获取商品详情
```
GET /api/goods/detail/<goods_id>
```

### 4. 保存商品
```
POST /api/goods/save
Body:
{
  "id": 商品ID,
  "title": "商品标题",
  "main_image": "主图URL",
  "image_list": ["图片URL数组"]
}
```

### 5. 批量保存商品
```
POST /api/goods/batch-save
Body:
{
  "goods_ids": [商品ID数组]
}
```

## 使用说明

### 检查商品

1. 在商品列表中浏览商品
2. 查看每个商品的主图和第三张轮播图
3. 检查标题是否正确

### 编辑商品

1. 点击商品卡片上的"编辑"按钮
2. 在编辑对话框中：
   - 修改标题（如需要）
   - 修改主图URL，或从轮播图中选择一张作为主图
   - 调整轮播图顺序（点击图片选中，使用上移/下移按钮）
   - 添加或删除轮播图

### 批量保存

1. 勾选需要保存的商品
2. 点击"批量保存"按钮
3. 确认后系统会批量调用保存接口

## 配置说明

### 数据库配置

在 `backend/.env` 或 Docker 的 `.env` 文件中配置：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=temu_baodan
```

### 保存接口配置

```env
SAVE_API_URL=http://temebaodan.all369.cn/api/pc/savegoods
```

### 认证信息（如果需要）

如果保存接口需要认证，可以在 `backend/app.py` 的 `save_goods` 和 `batch_save_goods` 函数中添加：

```python
headers['Authorization'] = 'Bearer your_token'
# 或
cookies = {'token': 'your_cookie'}
```

## 注意事项

1. **数据库连接**: 确保MySQL服务正在运行，并且数据库和表已创建
2. **跨域问题**: 如果前端和后端不在同一域名，后端已配置CORS，但前端需要修改API_BASE_URL
3. **图片加载**: 如果图片URL无法访问，会显示占位图
4. **批量保存**: 批量保存时，如果某个商品保存失败，会在控制台输出错误信息

## 开发计划

- [ ] 添加图片上传功能
- [ ] 添加商品状态筛选（已上传/未上传）
- [ ] 添加操作日志记录
- [ ] 优化批量保存的错误处理
- [ ] 添加数据统计功能

## 许可证

MIT
