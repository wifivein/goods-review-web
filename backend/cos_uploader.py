"""
腾讯云COS图片上传工具
用于将本地图片上传到腾讯云COS对象存储
"""
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class COSUploader:
    def __init__(self):
        """初始化COS客户端"""
        # 从环境变量读取配置
        self.secret_id = os.getenv('COS_SECRET_ID', '')
        self.secret_key = os.getenv('COS_SECRET_KEY', '')
        self.region = os.getenv('COS_REGION', 'ap-beijing')  # 默认北京
        self.bucket = os.getenv('COS_BUCKET', '')
        self.domain = os.getenv('COS_DOMAIN', '')  # CDN域名，可选
        
        if not self.secret_id or not self.secret_key or not self.bucket:
            raise ValueError("请配置COS_SECRET_ID、COS_SECRET_KEY和COS_BUCKET环境变量")
        
        # 初始化配置
        config = CosConfig(
            Region=self.region,
            SecretId=self.secret_id,
            SecretKey=self.secret_key,
            Scheme='https'  # 使用https
        )
        
        # 初始化客户端
        self.client = CosS3Client(config)
        self.bucket_name = self.bucket
    
    def upload_file(self, local_path, cos_path=None):
        """
        上传单个文件到COS
        
        Args:
            local_path: 本地文件路径
            cos_path: COS中的路径（如果不指定，则使用文件名）
        
        Returns:
            dict: {
                'success': bool,
                'url': str,  # 访问URL
                'cos_path': str,  # COS路径
                'error': str  # 错误信息（如果有）
            }
        """
        try:
            if not os.path.exists(local_path):
                return {
                    'success': False,
                    'error': f'文件不存在: {local_path}'
                }
            
            # 如果没有指定COS路径，使用文件名
            if cos_path is None:
                cos_path = os.path.basename(local_path)
            
            # 确保COS路径以/开头
            if not cos_path.startswith('/'):
                cos_path = '/' + cos_path
            
            # 上传文件
            response = self.client.upload_file(
                Bucket=self.bucket_name,
                LocalFilePath=local_path,
                Key=cos_path,
                EnableMD5=False
            )
            
            # 构建访问URL
            if self.domain:
                # 使用CDN域名
                url = f"https://{self.domain}{cos_path}"
            else:
                # 使用COS默认域名
                url = f"https://{self.bucket_name}.cos.{self.region}.myqcloud.com{cos_path}"
            
            return {
                'success': True,
                'url': url,
                'cos_path': cos_path,
                'etag': response.get('ETag', '')
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def upload_product_image(self, local_path, goods_id, image_type='carousel', index=0):
        """
        上传商品图片（按商品ID组织目录结构）
        
        Args:
            local_path: 本地文件路径
            goods_id: 商品ID
            image_type: 图片类型 ('carousel', 'main', 'sku')
            index: 图片索引（轮播图序号）
        
        Returns:
            dict: 上传结果
        """
        # 获取文件扩展名
        ext = os.path.splitext(local_path)[1]
        
        # 构建COS路径：product_images/{goods_id}/{image_type}_{index}{ext}
        if image_type == 'carousel':
            cos_path = f"product_images/{goods_id}/carousel_{index:03d}{ext}"
        elif image_type == 'main':
            cos_path = f"product_images/{goods_id}/main{ext}"
        else:
            cos_path = f"product_images/{goods_id}/{image_type}_{index}{ext}"
        
        return self.upload_file(local_path, cos_path)
    
    def batch_upload(self, local_paths, cos_base_path=''):
        """
        批量上传文件
        
        Args:
            local_paths: 本地文件路径列表
            cos_base_path: COS基础路径（可选）
        
        Returns:
            list: 上传结果列表
        """
        results = []
        for local_path in local_paths:
            if cos_base_path:
                filename = os.path.basename(local_path)
                cos_path = f"{cos_base_path}/{filename}" if cos_base_path else filename
            else:
                cos_path = None
            
            result = self.upload_file(local_path, cos_path)
            results.append({
                'local_path': local_path,
                **result
            })
        
        return results
    
    def test_connection(self):
        """
        测试COS连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 尝试列出bucket（只列出1个对象，用于测试）
            response = self.client.list_objects(
                Bucket=self.bucket_name,
                MaxKeys=1
            )
            return True
        except Exception as e:
            print(f"COS连接测试失败: {str(e)}")
            return False


def main():
    """测试脚本：上传几张图片"""
    import argparse
    
    parser = argparse.ArgumentParser(description='上传图片到腾讯云COS')
    parser.add_argument('--files', nargs='+', help='要上传的本地文件路径')
    parser.add_argument('--test', action='store_true', help='测试COS连接')
    parser.add_argument('--goods-id', type=str, help='商品ID（用于组织目录结构）')
    
    args = parser.parse_args()
    
    try:
        uploader = COSUploader()
        
        # 测试连接
        if args.test:
            print("正在测试COS连接...")
            if uploader.test_connection():
                print("✅ COS连接成功！")
            else:
                print("❌ COS连接失败，请检查配置")
            return
        
        # 上传文件
        if args.files:
            print(f"准备上传 {len(args.files)} 个文件...")
            results = []
            
            for i, file_path in enumerate(args.files):
                print(f"\n[{i+1}/{len(args.files)}] 上传: {file_path}")
                
                if args.goods_id:
                    # 使用商品ID组织目录
                    result = uploader.upload_product_image(
                        file_path, 
                        args.goods_id, 
                        image_type='carousel',
                        index=i
                    )
                else:
                    # 直接上传
                    result = uploader.upload_file(file_path)
                
                if result['success']:
                    print(f"  ✅ 上传成功")
                    print(f"  📍 COS路径: {result['cos_path']}")
                    print(f"  🔗 访问URL: {result['url']}")
                else:
                    print(f"  ❌ 上传失败: {result.get('error', '未知错误')}")
                
                results.append(result)
            
            # 汇总
            success_count = sum(1 for r in results if r['success'])
            print(f"\n{'='*50}")
            print(f"上传完成: {success_count}/{len(results)} 成功")
            
            if success_count > 0:
                print("\n成功上传的文件URL:")
                for r in results:
                    if r['success']:
                        print(f"  - {r['url']}")
        else:
            print("请指定要上传的文件，使用 --files 参数")
            print("示例: python cos_uploader.py --files image1.jpg image2.jpg")
            print("或: python cos_uploader.py --files image1.jpg --goods-id 12345")
    
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        print("\n请设置以下环境变量:")
        print("  - COS_SECRET_ID: 腾讯云SecretId")
        print("  - COS_SECRET_KEY: 腾讯云SecretKey")
        print("  - COS_REGION: COS地域（如: ap-beijing）")
        print("  - COS_BUCKET: COS存储桶名称")
        print("  - COS_DOMAIN: CDN域名（可选）")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
