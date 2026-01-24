# 腾讯云COS快速开始

## 🚀 3步快速测试

### 第1步：配置环境变量

编辑 `/opt/goods_review_web/docker/.env` 文件，添加：

```bash
COS_SECRET_ID=你的SecretId
COS_SECRET_KEY=你的SecretKey
COS_REGION=ap-beijing
COS_BUCKET=你的存储桶名称
COS_DOMAIN=你的CDN域名（可选）
```

### 第2步：重启后端容器（加载环境变量）

```bash
cd /opt/goods_review_web
docker-compose -f docker/docker-compose.yml restart backend
```

### 第3步：运行测试脚本

```bash
docker exec -it goods_review_backend python3 /app/test_cos_upload.py
```

脚本会自动：
- ✅ 检查配置
- ✅ 测试连接
- ✅ 上传3张测试图片
- ✅ 显示访问URL

## 📝 手动上传测试

如果想手动指定图片上传：

```bash
# 进入容器
docker exec -it goods_review_backend bash

# 上传单张图片
python3 /app/cos_uploader.py --files /opt/product_images/601/099/512/601099512498946/002_1765008923991-ar8ly7.jpg

# 上传多张图片
python3 /app/cos_uploader.py --files \
  /opt/product_images/601/099/512/601099512498946/002_1765008923991-ar8ly7.jpg \
  /opt/product_images/601/099/512/601099512498946/005_1765008923993-p0nq1l.jpg \
  /opt/product_images/601/099/512/601099512498946/003_1765008923992-rmpekn.jpg

# 按商品ID组织目录上传
python3 /app/cos_uploader.py --files \
  /opt/product_images/601/099/512/601099512498946/002_1765008923991-ar8ly7.jpg \
  --goods-id 601099512498946
```

## 🔍 获取配置信息

### 1. SecretId 和 SecretKey
- 登录 [腾讯云控制台](https://console.cloud.tencent.com/)
- 进入 [访问管理 -> API密钥管理](https://console.cloud.tencent.com/cam/capi)
- 创建或查看密钥

### 2. Region（地域）
- 进入 [对象存储COS](https://console.cloud.tencent.com/cos)
- 查看存储桶的地域，如：`ap-beijing`（北京）、`ap-shanghai`（上海）等

### 3. Bucket（存储桶名称）
- 在COS控制台查看存储桶名称
- 格式如：`my-bucket-1234567890`

### 4. Domain（CDN域名，可选）
- 如果配置了CDN加速，填写CDN域名
- 如：`cdn.example.com`
- 如果不配置，会使用COS默认域名

## ✅ 测试成功后的输出示例

```
============================================================
腾讯云COS图片上传测试
============================================================

1. 初始化COS客户端...
   ✅ 初始化成功

2. 测试COS连接...
   ✅ 连接成功

3. 查找测试图片...
   找到 3 张测试图片:
     - /opt/product_images/601/099/512/601099512498946/002_1765008923991-ar8ly7.jpg
     - /opt/product_images/601/099/512/601099512498946/005_1765008923993-p0nq1l.jpg
     - /opt/product_images/601/099/512/601099512498946/003_1765008923992-rmpekn.jpg

4. 开始上传测试图片...
------------------------------------------------------------

[1/3] 上传: 002_1765008923991-ar8ly7.jpg
   ✅ 上传成功
   📍 COS路径: /test/002_1765008923991-ar8ly7.jpg
   🔗 访问URL: https://your-bucket.cos.ap-beijing.myqcloud.com/test/002_1765008923991-ar8ly7.jpg

...

============================================================
测试完成: 3/3 成功

✅ 成功上传的文件，可以在浏览器中访问:
   https://your-bucket.cos.ap-beijing.myqcloud.com/test/002_1765008923991-ar8ly7.jpg
   ...
```

## 🎯 下一步

测试成功后，可以：
1. 批量迁移现有图片（13.5万张）
2. 集成到后端API（新图片自动上传）
3. 更新前端代码（使用COS URL）
