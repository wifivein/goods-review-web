# 腾讯云COS对象存储集成指南

## 📋 前置准备

1. **创建COS存储桶**
   - 登录腾讯云控制台
   - 进入 [对象存储COS](https://console.cloud.tencent.com/cos)
   - 创建存储桶（Bucket）
   - 记录存储桶名称和地域（Region）

2. **获取API密钥**
   - 进入 [访问管理 -> API密钥管理](https://console.cloud.tencent.com/cam/capi)
   - 创建或查看SecretId和SecretKey

3. **配置CDN（可选）**
   - 如果需要CDN加速，可以配置CDN域名
   - 记录CDN域名

## ⚙️ 配置步骤

### 1. 配置环境变量

编辑 `docker/.env` 文件，添加以下配置：

```bash
# 腾讯云COS配置
COS_SECRET_ID=你的SecretId
COS_SECRET_KEY=你的SecretKey
COS_REGION=ap-beijing  # 存储桶地域，如：ap-beijing, ap-shanghai等
COS_BUCKET=你的存储桶名称
COS_DOMAIN=你的CDN域名  # 可选，如果配置了CDN
```

### 2. 安装依赖

```bash
cd goods_review_web/backend
pip install -r requirements.txt
```

或者在Docker容器中：

```bash
docker exec -it goods_review_backend pip install cos-python-sdk-v5==1.9.25
```

### 3. 测试上传

#### 方法1：使用测试脚本（推荐）

```bash
# 在服务器上执行
cd /opt/goods_review_web/backend
python3 test_cos_upload.py
```

脚本会自动：
- 检查环境变量配置
- 测试COS连接
- 查找几张测试图片
- 上传到COS的 `test/` 目录

#### 方法2：使用上传工具

```bash
# 上传单张图片
python3 cos_uploader.py --files /opt/product_images/601/099/512/image.jpg

# 上传多张图片
python3 cos_uploader.py --files image1.jpg image2.jpg image3.jpg

# 按商品ID组织目录结构上传
python3 cos_uploader.py --files image1.jpg --goods-id 12345

# 测试连接
python3 cos_uploader.py --test
```

## 📁 目录结构

上传到COS后的目录结构：

```
product_images/
├── {goods_id}/
│   ├── carousel_000.jpg  # 轮播图第1张
│   ├── carousel_001.jpg  # 轮播图第2张
│   ├── carousel_002.jpg  # 轮播图第3张
│   └── main.jpg          # 主图
└── test/                 # 测试目录
    ├── image1.jpg
    └── image2.jpg
```

## 🔗 访问URL格式

- **使用CDN域名**（如果配置了COS_DOMAIN）:
  ```
  https://your-cdn-domain.com/product_images/{goods_id}/carousel_000.jpg
  ```

- **使用COS默认域名**（如果未配置CDN）:
  ```
  https://{bucket}.cos.{region}.myqcloud.com/product_images/{goods_id}/carousel_000.jpg
  ```

## 🚀 下一步

测试成功后，可以：

1. **批量迁移现有图片**（编写迁移脚本）
2. **集成到后端API**（新图片自动上传到COS）
3. **更新前端代码**（使用COS URL显示图片）
4. **配置Nginx**（可选：保留本地图片作为备份）

## ⚠️ 注意事项

1. **费用**：
   - 存储：50G免费额度
   - 流量：外网访问会产生流量费用，内网访问免费
   - 建议配置CDN以降低流量成本

2. **权限**：
   - 确保存储桶的访问权限配置正确
   - 建议使用私有读写，通过CDN或临时URL访问

3. **安全性**：
   - 不要将SecretKey提交到代码仓库
   - 使用环境变量或密钥管理服务

## 📞 问题排查

如果上传失败，检查：

1. **环境变量是否正确配置**
   ```bash
   docker exec goods_review_backend env | grep COS
   ```

2. **网络连接是否正常**
   ```bash
   docker exec goods_review_backend ping cos.ap-beijing.myqcloud.com
   ```

3. **存储桶权限是否正确**
   - 检查存储桶的读写权限
   - 检查API密钥的权限

4. **查看详细错误信息**
   ```bash
   python3 test_cos_upload.py
   ```
