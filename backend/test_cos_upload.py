#!/usr/bin/env python3
"""
快速测试脚本：上传几张图片到COS
"""
import os
import sys
from pathlib import Path
from cos_uploader import COSUploader

def find_test_images(base_path='/opt/product_images', limit=3):
    """查找几张测试图片"""
    test_images = []
    
    # 查找前几张图片
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                test_images.append(full_path)
                if len(test_images) >= limit:
                    return test_images
    
    return test_images

def main():
    print("=" * 60)
    print("腾讯云COS图片上传测试")
    print("=" * 60)
    
    # 检查环境变量
    required_vars = ['COS_SECRET_ID', 'COS_SECRET_KEY', 'COS_BUCKET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"\n❌ 缺少环境变量: {', '.join(missing_vars)}")
        print("\n请先配置环境变量（在 .env 文件或 docker-compose.yml 中）:")
        print("  COS_SECRET_ID=你的SecretId")
        print("  COS_SECRET_KEY=你的SecretKey")
        print("  COS_REGION=ap-beijing  # 或其他地域")
        print("  COS_BUCKET=你的存储桶名称")
        print("  COS_DOMAIN=你的CDN域名  # 可选")
        return
    
    try:
        # 初始化上传器
        print("\n1. 初始化COS客户端...")
        uploader = COSUploader()
        print("   ✅ 初始化成功")
        
        # 测试连接
        print("\n2. 测试COS连接...")
        if uploader.test_connection():
            print("   ✅ 连接成功")
        else:
            print("   ❌ 连接失败，请检查配置")
            return
        
        # 查找测试图片
        print("\n3. 查找测试图片...")
        test_images = find_test_images(limit=3)
        
        if not test_images:
            print("   ❌ 未找到测试图片")
            print("   请手动指定图片路径")
            return
        
        print(f"   找到 {len(test_images)} 张测试图片:")
        for img in test_images:
            print(f"     - {img}")
        
        # 上传测试
        print("\n4. 开始上传测试图片...")
        print("-" * 60)
        
        results = []
        for i, img_path in enumerate(test_images):
            print(f"\n[{i+1}/{len(test_images)}] 上传: {os.path.basename(img_path)}")
            
            # 使用测试目录
            result = uploader.upload_file(
                img_path,
                cos_path=f"test/{os.path.basename(img_path)}"
            )
            
            if result['success']:
                print(f"   ✅ 上传成功")
                print(f"   📍 COS路径: {result['cos_path']}")
                print(f"   🔗 访问URL: {result['url']}")
            else:
                print(f"   ❌ 上传失败: {result.get('error', '未知错误')}")
            
            results.append(result)
        
        # 汇总
        print("\n" + "=" * 60)
        success_count = sum(1 for r in results if r['success'])
        print(f"测试完成: {success_count}/{len(results)} 成功")
        
        if success_count > 0:
            print("\n✅ 成功上传的文件，可以在浏览器中访问:")
            for r in results:
                if r['success']:
                    print(f"   {r['url']}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
