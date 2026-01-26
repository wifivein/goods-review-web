"""
商品检查和修正系统 - Flask后端
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import json
import urllib.parse
import requests
from datetime import datetime
import os
from dotenv import load_dotenv
import copy

load_dotenv()

app = Flask(__name__)
CORS(app)  # 允许跨域

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '101.33.241.82'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'root'),
    'database': os.getenv('DB_NAME', 'temu_baodan'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 外部 API 配置
SAVE_API_URL = "https://gwfpod.com/api/collect/product/batch_update"
INFRINGEMENT_API_URL = "https://gwfpod.com/api/collect/product/batch_infringement_detection"
# 使用您抓包提供的新 Token
DEFAULT_AUTH_TOKEN = "13bc0f9d096f277bcce36a25b274b74a0c7c6fe3"

# 毛毯标准规格图 URL（审核通过时替换第 3 张图）
BLANKET_SPEC_IMAGE_URL = "https://img.kwcdn.com/product/20195053a14/c2ddafb8-2eee-497c-9c81-c45254e903bf_800x800.png"


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def ensure_sku_dimensions(sku_list):
    """
    确保SKU列表中的每个SKU都有len、width、height字段
    如果缺失，尝试从size字段解析
    返回处理后的SKU列表
    """
    if not isinstance(sku_list, list):
        return sku_list
    
    import re
    updated_sku_list = []
    
    for sku in sku_list:
        if not isinstance(sku, dict):
            updated_sku_list.append(sku)
            continue
        
        # 深拷贝确保保留所有原始字段
        updated_sku = copy.deepcopy(sku)
        
        # 如果len、width、height字段缺失或为空，尝试从size字段解析
        if ('len' not in updated_sku or updated_sku.get('len') is None or updated_sku.get('len') == '') or \
           ('width' not in updated_sku or updated_sku.get('width') is None or updated_sku.get('width') == '') or \
           ('height' not in updated_sku or updated_sku.get('height') is None or updated_sku.get('height') == ''):
            # 尝试从size字段解析（格式：35.00x25.00x2.00 cm）
            size_value = updated_sku.get('size', '')
            if size_value and isinstance(size_value, str):
                # 匹配格式：数字x数字x数字（可能有单位）
                match = re.match(r'(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)', size_value)
                if match:
                    len_val, width_val, height_val = match.groups()
                    # 只在字段不存在或为空时才设置（不覆盖已有值）
                    if 'len' not in updated_sku or updated_sku.get('len') is None or updated_sku.get('len') == '':
                        updated_sku['len'] = f"{float(len_val):.2f}"
                    if 'width' not in updated_sku or updated_sku.get('width') is None or updated_sku.get('width') == '':
                        updated_sku['width'] = f"{float(width_val):.2f}"
                    if 'height' not in updated_sku or updated_sku.get('height') is None or updated_sku.get('height') == '':
                        updated_sku['height'] = f"{float(height_val):.2f}"
        
        # 确保数值字段是有效的字符串格式
        numeric_string_fields = ['len', 'width', 'height', 'suggestedPrice', 'supplierPrice', 'weight']
        for field in numeric_string_fields:
            field_value = updated_sku.get(field)
            # 如果字段不存在、为None、或为空字符串，才设置默认值
            if field not in updated_sku or field_value is None or field_value == '':
                if field in ['len', 'width', 'height']:
                    # 尺寸字段设为"0.00"（只有在确实无法获取值时才设置）
                    updated_sku[field] = '0.00'
                else:
                    updated_sku[field] = '0'
            # 如果字段存在且有值，确保是字符串格式
            else:
                try:
                    # 验证是否为有效数字，如果是则转换为字符串格式
                    float_val = float(field_value)
                    if field in ['len', 'width', 'height']:
                        # 尺寸字段保留两位小数
                        updated_sku[field] = f"{float_val:.2f}"
                    else:
                        # 价格和重量字段
                        if float_val == int(float_val):
                            updated_sku[field] = str(int(float_val))
                        else:
                            updated_sku[field] = str(float_val)
                except (ValueError, TypeError):
                    # 如果无法转换为数字，保持原值（可能是字符串格式的数字）
                    updated_sku[field] = str(field_value)
        
        updated_sku_list.append(updated_sku)
    
    return updated_sku_list


def save_goods_to_external_api(goods_id):
    """
    将修改后的商品数据回存到新版软件的 API (JSON 格式)
    """
    try:
        # 获取完整商品数据
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 从 temu_goods_v2 读取
        sql = """
            SELECT 
                api_id as id, product_name, extcode, 
                carousel_pic_urls, sku_list
            FROM temu_goods_v2 
            WHERE id = %s
        """
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            cursor.close()
            conn.close()
            return {'success': False, 'error': '商品不存在'}
            
        # 解析 JSON 字段
        try:
            carousel_pic_urls = json.loads(goods['carousel_pic_urls']) if isinstance(goods['carousel_pic_urls'], str) else goods['carousel_pic_urls']
            sku_list = json.loads(goods['sku_list']) if isinstance(goods['sku_list'], str) else goods['sku_list']
        except:
            carousel_pic_urls = []
            sku_list = []

        # 映射 SKU 字段到新 API 格式
        processed_sku_list = []
        for sku in sku_list:
            if not isinstance(sku, dict): continue
            
            # 新 API 字段映射
            new_sku = {
                "productSkuId": sku.get("productSkuId") or sku.get("id"),
                "pic_url": sku.get("pic_url") or sku.get("pic") or sku.get("image") or (carousel_pic_urls[0] if carousel_pic_urls else ""),
                "volumeLen": float(sku.get("volumeLen") or sku.get("len") or 0),
                "volumeWidth": float(sku.get("volumeWidth") or sku.get("width") or 0),
                "volumeHeight": float(sku.get("volumeHeight") or sku.get("height") or 0),
                "weightValue": float(sku.get("weightValue") or sku.get("weight") or 0),
                "supplierPrice": float(sku.get("supplierPrice") or 0),
                "suggestedPrice": float(sku.get("suggestedPrice") or 0),
                "imageIndex": sku.get("imageIndex")
            }
            
            # 处理规格名称 (新 API 中似乎直接用数字 ID 作为 key，如 "3001")
            # 我们保留原始 sku 中所有不冲突的字段，以防有动态规格 key
            for k, v in sku.items():
                if k not in ["len", "width", "height", "weight", "pic", "image", "id", "volumeLen", "volumeWidth", "volumeHeight", "weightValue", "pic_url"]:
                    new_sku[k] = v
            
            processed_sku_list.append(new_sku)

        # 构建新版 API 的 JSON Body
        payload = {
            "products": [
                {
                    "id": goods['id'], # 这里的 id 是原软件的 api_id
                    "product_name": goods['product_name'],
                    "extcode": goods['extcode'] or "",
                    "carousel_pic_urls": carousel_pic_urls,
                    "sku_list": processed_sku_list
                }
            ]
        }
        
        cursor.close()
        conn.close()
        
        # 发送请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Authorization': os.getenv('AUTH_TOKEN', DEFAULT_AUTH_TOKEN)
        }
        
        print(f"[DEBUG] 正在回存商品 {goods_id} 到新 API...")
        response = requests.post(
            SAVE_API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get('code') == 0:
                print(f"[SUCCESS] 商品 {goods_id} 回存成功")
                return {'success': True, 'data': res_json}
            else:
                print(f"[ERROR] API 返回错误: {res_json.get('msg')}")
                return {'success': False, 'error': res_json.get('msg')}
        else:
            print(f"[ERROR] HTTP 错误: {response.status_code}")
            return {'success': False, 'error': f'HTTP {response.status_code}'}
            
    except Exception as e:
        print(f"[EXCEPTION] 回存失败: {str(e)}")
        return {'success': False, 'error': str(e)}


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({'status': 'ok', 'message': '服务运行正常'})


@app.route('/api/goods/statistics', methods=['GET'])
def get_statistics():
    """获取商品统计信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. 预处理（process_status = 0 或 1，且未发布）
        preprocessing_sql = """
            SELECT COUNT(*) as count
            FROM temu_goods_v2
            WHERE process_status IN (0, 1) AND is_publish = 0
        """
        cursor.execute(preprocessing_sql)
        preprocessing_count = cursor.fetchone()['count']
        
        # 2. 待审核（process_status = 2 且 review_status = 0，且未发布）
        pending_review_sql = """
            SELECT COUNT(*) as count
            FROM temu_goods_v2
            WHERE process_status = 2 AND review_status = 0 AND is_publish = 0
        """
        cursor.execute(pending_review_sql)
        pending_review_count = cursor.fetchone()['count']
        
        # 3. 待上传（process_status = 2 且 review_status = 1，且未发布；排除侵权疑似/侵权 infringement_status=2,3）
        pending_upload_sql = """
            SELECT COUNT(*) as count
            FROM temu_goods_v2
            WHERE process_status = 2 AND review_status = 1 AND is_publish = 0
            AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3))
        """
        cursor.execute(pending_upload_sql)
        pending_upload_count = cursor.fetchone()['count']
        
        # 4. 已废弃（process_status = 2 且 review_status = 2，且未发布）
        discarded_sql = """
            SELECT COUNT(*) as count 
            FROM temu_goods_v2 
            WHERE process_status = 2 AND review_status = 2 AND is_publish = 0
        """
        cursor.execute(discarded_sql)
        discarded_count = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {
                'preprocessing': preprocessing_count,
                'pending_review': pending_review_count,
                'pending_upload': pending_upload_count,
                'discarded': discarded_count
            }
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/goods/first-pending-upload', methods=['GET'])
def get_first_pending_upload():
    """获取第一个待上传商品的ID和位置信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询第一个待上传商品（process_status=2，review_status=1，且未发布；排除侵权疑似/侵权）
        sql = """
            SELECT id, product_id as goods_id, create_time
            FROM temu_goods_v2
            WHERE process_status = 2
            AND review_status = 1
            AND is_publish = 0
            AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3))
            ORDER BY create_time DESC
            LIMIT 1
        """
        cursor.execute(sql)
        result = cursor.fetchone()
        
        if result:
            # 计算该商品在所有商品中的排名
            create_time = result.get('create_time')
            rank = 1  
            
            if create_time is not None:
                try:
                    rank_sql = """
                        SELECT COUNT(*) as cnt
                        FROM temu_goods_v2
                        WHERE process_status = 2 AND review_status = 1 AND is_publish = 0
                        AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3))
                        AND create_time > %s
                    """
                    cursor.execute(rank_sql, (create_time,))
                    rank_result = cursor.fetchone()
                    rank = rank_result['cnt'] + 1 if rank_result and rank_result.get('cnt') is not None else 1
                except Exception as e:
                    print(f"[ERROR] 计算排名失败: {str(e)}")
                    rank = 1 
            
            cursor.close()
            conn.close()
            
            return jsonify({
                'code': 0,
                'message': 'success',
                'data': {
                    'id': result['id'],
                    'goods_id': result['goods_id'],
                    'create_time': create_time.isoformat() if hasattr(create_time, 'isoformat') else str(create_time),
                    'rank': rank  
                }
            })
        else:
            cursor.close()
            conn.close()
            return jsonify({
                'code': -1,
                'message': '没有找到待上传的商品'
            }), 404
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"[ERROR] get_first_pending_upload 失败: {error_msg}")
        print(f"[ERROR] 错误堆栈:\n{error_trace}")
        # 确保关闭数据库连接
        try:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
        except:
            pass
        return jsonify({
            'code': -1,
            'message': f'查询失败: {error_msg}'
        }), 500


@app.route('/api/goods/list', methods=['GET'])
def get_goods_list():
    """获取商品列表（支持分页和搜索）"""
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        search = request.args.get('search', '').strip()
        user_id = request.args.get('user_id', '').strip()
        review_status = request.args.get('review_status')
        process_status = request.args.get('process_status')
        order_by = request.args.get('order_by', 'time_desc')
        
        offset = (page - 1) * page_size
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询条件
        where_conditions = []
        params = []
        
        # 只显示未发布的商品（is_publish = 0）
        where_conditions.append("is_publish = 0")
        # 排除侵权检测为疑似/侵权（infringement_status=2,3）的商品，不再展示、不再上传
        where_conditions.append("(infringement_status IS NULL OR infringement_status NOT IN (2, 3))")
        
        if search:
            where_conditions.append("product_name LIKE %s")
            search_param = f"%{search}%"
            params.append(search_param)
        
        if user_id:
            where_conditions.append("master_user_id = %s")
            params.append(user_id)

        if review_status is not None:
            where_conditions.append("review_status = %s")
            params.append(review_status)

        if process_status is not None:
            where_conditions.append("process_status = %s")
            params.append(process_status)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # 排序逻辑
        order_clause = "ORDER BY create_time DESC"
        if order_by == 'id_asc':
            order_clause = "ORDER BY id ASC"
        elif order_by == 'api_id_asc':
            order_clause = "ORDER BY api_id ASC"
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) as total FROM temu_goods_v2 {where_clause}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()['total']
        
        # 查询列表
        list_sql = f"""
            SELECT 
                id, master_user_id as user_id, product_id as goods_id, 
                product_name as title, product_name as name, 
                carousel_pic_urls as image_list,
                create_time as create_time_str, update_time,
                is_publish as isupload, process_status as uploadstatus, 
                review_status,
                sale_count as soldcount
            FROM temu_goods_v2 
            {where_clause}
            {order_clause}
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        cursor.execute(list_sql, params)
        goods_list = cursor.fetchall()
        
        # 处理JSON字段和补全main_image
        for goods in goods_list:
            # 处理 image_list (carousel_pic_urls)
            if goods.get('image_list'):
                try:
                    img_list = json.loads(goods['image_list']) if isinstance(goods['image_list'], str) else goods['image_list']
                    goods['image_list'] = img_list
                    # 补全 main_image (取第一张图)
                    goods['main_image'] = img_list[0] if img_list and len(img_list) > 0 else ""
                    goods['cover'] = goods['main_image']
                except:
                    goods['image_list'] = []
                    goods['main_image'] = ""
                    goods['cover'] = ""
            else:
                goods['image_list'] = []
                goods['main_image'] = ""
                goods['cover'] = ""
            
            # 兼容处理 create_time_str
            if isinstance(goods.get('create_time_str'), datetime):
                goods['create_time_str'] = goods['create_time_str'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {
                'list': goods_list,
                'total': total,
                'page': page,
                'page_size': page_size
            }
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/goods/detail/<int:goods_id>', methods=['GET'])
def get_goods_detail(goods_id):
    """获取商品详情"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 使用别名映射到前端习惯的字段名
        sql = """
            SELECT 
                id, master_user_id as user_id, product_id as goods_id, 
                product_name as title, product_name as name, 
                carousel_pic_urls as image_list,
                sku_list, sku_specs as spec,
                create_time, update_time,
                is_publish as isupload, process_status as uploadstatus,
                review_status,
                sale_count as soldcount, origin_product_url as url,
                group_id, ref_product_template_id, ref_product_size_template_id,
                extcode, create_by, create_dept_id, malls,
                product_template, product_size_template, group_data as product_spec_map
            FROM temu_goods_v2 
            WHERE id = %s
        """
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 处理JSON字段和补全main_image
        json_fields = ['image_list', 'sku_list', 'spec', 'malls', 
                      'product_template', 'product_size_template', 'product_spec_map']
        
        for field in json_fields:
            if goods.get(field):
                try:
                    goods[field] = json.loads(goods[field]) if isinstance(goods[field], str) else goods[field]
                except:
                    goods[field] = [] if field.endswith('_list') or field == 'image_list' else {}
        
        # 补全 main_image 和 cover
        img_list = goods.get('image_list', [])
        goods['main_image'] = img_list[0] if img_list and len(img_list) > 0 else ""
        goods['cover'] = goods['main_image']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': goods
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/goods/save', methods=['POST'])
def save_goods():
    """保存商品修改（调用外部接口）"""
    try:
        data = request.json
        goods_id = data.get('id')
        
        if not goods_id:
            return jsonify({
                'code': -1,
                'message': '商品ID不能为空'
            }), 400
        
        # 从数据库获取完整商品数据
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = "SELECT id, product_name, carousel_pic_urls FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            cursor.close()
            conn.close()
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 处理现有图片列表
        current_image_list = []
        if goods.get('carousel_pic_urls'):
            try:
                current_image_list = json.loads(goods['carousel_pic_urls']) if isinstance(goods['carousel_pic_urls'], str) else goods['carousel_pic_urls']
            except:
                current_image_list = []
        
        # 构建更新
        update_fields = []
        update_params = []
        
        # 如果有标题修改
        if 'title' in data:
            update_fields.append("product_name = %s")
            update_params.append(data['title'])
            
        # 如果有图片列表修改
        if 'image_list' in data:
            new_image_list = data['image_list']
            # 如果同时传了 main_image，确保它是第一张
            if 'main_image' in data and new_image_list:
                if new_image_list[0] != data['main_image']:
                    # 尝试在列表中找到 main_image 并移动到第一位，或者直接覆盖
                    if data['main_image'] in new_image_list:
                        new_image_list.remove(data['main_image'])
                    new_image_list.insert(0, data['main_image'])
            
            update_fields.append("carousel_pic_urls = %s")
            update_params.append(json.dumps(new_image_list, ensure_ascii=False))
        elif 'main_image' in data and current_image_list:
            # 只修改了主图
            new_image_list = list(current_image_list)
            if new_image_list[0] != data['main_image']:
                if data['main_image'] in new_image_list:
                    new_image_list.remove(data['main_image'])
                new_image_list.insert(0, data['main_image'])
            
            update_fields.append("carousel_pic_urls = %s")
            update_params.append(json.dumps(new_image_list, ensure_ascii=False))

        # 新增：如果有 SKU 列表修改
        if 'sku_list' in data:
            update_fields.append("sku_list = %s")
            update_params.append(json.dumps(data['sku_list'], ensure_ascii=False))
            
        # 执行数据库更新
        if update_fields:
            update_sql = "UPDATE temu_goods_v2 SET " + ", ".join(update_fields) + " WHERE id = %s"
            update_params.append(goods_id)
            cursor.execute(update_sql, update_params)
            conn.commit()
        
        cursor.close()
        conn.close()
        
        # 使用修复后的 save_goods_to_external_api 函数回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        if save_result['success']:
            return jsonify({
                'code': 0,
                'message': '保存成功',
                'data': save_result
            })
        else:
            return jsonify({
                'code': -1,
                'message': f'保存失败: {save_result.get("error", "未知错误")}',
                'data': save_result
            }), 500
            
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'保存失败: {str(e)}'
        }), 500


@app.route('/api/goods/batch-save', methods=['POST'])
def batch_save_goods():
    """批量保存商品（切换到 v2）"""
    try:
        data = request.json
        goods_ids = data.get('goods_ids', [])
        
        if not goods_ids:
            return jsonify({
                'code': -1,
                'message': '商品ID列表不能为空'
            }), 400
        
        results = []
        errors = []
        
        for goods_id in goods_ids:
            save_result = save_goods_to_external_api(goods_id)
            if save_result['success']:
                results.append({'id': goods_id, 'status': 'success'})
            else:
                errors.append({'id': goods_id, 'error': save_result.get('error', '未知错误')})
        
        return jsonify({
            'code': 0,
            'message': '批量保存完成',
            'data': {
                'success_count': len(results),
                'error_count': len(errors),
                'results': results,
                'errors': errors
            }
        })
        
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'批量保存失败: {str(e)}'
        }), 500


@app.route('/api/goods/approve', methods=['POST'])
def approve_goods():
    """审核通过商品（review_status 从 0 变成 1）。毛毯类替换第 3 张图为标准规格图；不足 3 张则作废。"""
    try:
        data = request.json
        goods_id = data.get('id')

        if not goods_id:
            return jsonify({'code': -1, 'message': '商品ID不能为空'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT id, api_id, product_name, carousel_pic_urls, sku_list FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()

        if not goods:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': '商品不存在'}), 404

        image_list = []
        if goods.get('carousel_pic_urls'):
            raw = goods['carousel_pic_urls']
            image_list = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(image_list, list):
            image_list = []

        # 不足 3 张：作废处理，不替换、不回存
        if len(image_list) < 3:
            title = (goods.get('product_name') or '') if isinstance(goods.get('product_name'), str) else ''
            if '【⚠️已废弃】' not in title and '⚠️废弃' not in title:
                title = '【⚠️已废弃】' + title
            update_sql = "UPDATE temu_goods_v2 SET product_name = %s, review_status = 2 WHERE id = %s"
            cursor.execute(update_sql, (title, goods_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({
                'code': 0,
                'message': '图片不足 3 张，已按废弃处理',
                'data': {'id': goods_id, 'review_status': 2}
            })

        # 替换第 3 张为标准规格图
        old_3rd = image_list[2]
        old_3rd_base = (old_3rd or '').split('?')[0]
        image_list[2] = BLANKET_SPEC_IMAGE_URL
        new_carousel = json.dumps(image_list, ensure_ascii=False)

        sku_list = []
        if goods.get('sku_list'):
            raw = goods['sku_list']
            sku_list = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(sku_list, list):
            sku_list = []

        if sku_list:
            updated = []
            for s in sku_list:
                if not isinstance(s, dict):
                    updated.append(s)
                    continue
                u = copy.deepcopy(s)
                hit = False
                if old_3rd_base:
                    for f in ('pic_url', 'pic', 'image'):
                        v = (u.get(f) or '').strip()
                        if v and (v.split('?')[0] == old_3rd_base):
                            hit = True
                            break
                if hit:
                    u['pic_url'] = u['pic'] = u['image'] = BLANKET_SPEC_IMAGE_URL
                updated.append(u)
            sku_list = ensure_sku_dimensions(updated)
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s, sku_list = %s, review_status = 1 WHERE id = %s"
            cursor.execute(update_sql, (new_carousel, json.dumps(sku_list, ensure_ascii=False), goods_id))
        else:
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s, review_status = 1 WHERE id = %s"
            cursor.execute(update_sql, (new_carousel, goods_id))
        conn.commit()
        cursor.close()
        conn.close()

        save_result = save_goods_to_external_api(goods_id)
        msg = '商品已审核通过，第3张已替换为标准规格图' + ('，回存成功' if save_result['success'] else '，但回存失败')

        api_id = goods.get('api_id')
        infringement_ok = False
        if api_id is not None:
            try:
                auth = os.getenv('AUTH_TOKEN', DEFAULT_AUTH_TOKEN)
                r = requests.post(
                    INFRINGEMENT_API_URL,
                    json={'ids': [int(api_id)]},
                    headers={'Content-Type': 'application/json', 'Authorization': auth},
                    timeout=10
                )
                infringement_ok = 200 <= r.status_code < 300
            except Exception as e:
                print(f"[WARN] 侵权检测提交失败 api_id={api_id}: {e}")
        if infringement_ok:
            msg += '，侵权检测已提交'

        return jsonify({
            'code': 0,
            'message': msg,
            'data': {'id': goods_id, 'review_status': 1}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': f'操作失败: {str(e)}'}), 500


@app.route('/api/goods/discard', methods=['POST'])
def discard_goods():
    """废弃商品（切换到 v2，更新 review_status=2）"""
    try:
        data = request.json
        goods_id = data.get('id')
        
        if not goods_id:
            return jsonify({
                'code': -1,
                'message': '商品ID不能为空'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前商品
        sql = "SELECT id, product_name, review_status FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            cursor.close()
            conn.close()
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 检查是否已经是废弃状态
        if goods.get('review_status') == 2:
            cursor.close()
            conn.close()
            return jsonify({
                'code': 0,
                'message': '商品已标记为废弃'
            })
        
        # 更新标题和状态
        current_title = goods.get('product_name', '')
        new_title = current_title
        if '⚠️已废弃' not in current_title and '⚠️废弃' not in current_title:
            new_title = '【⚠️已废弃】' + current_title
            
        update_sql = "UPDATE temu_goods_v2 SET product_name = %s, review_status = 2 WHERE id = %s"
        cursor.execute(update_sql, (new_title, goods_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # 回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        return jsonify({
            'code': 0,
            'message': '商品已标记为废弃' + ('，回存成功' if save_result['success'] else '，但回存失败'),
            'data': {'id': goods_id, 'title': new_title}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


@app.route('/api/goods/swap-image', methods=['POST'])
def swap_image():
    """交换轮播图中两张图片的位置（切换到 v2）"""
    try:
        data = request.json
        goods_id = data.get('id')
        source_index = data.get('source_index')  # 源图片索引
        target_index = data.get('target_index')  # 目标图片索引
        
        if not goods_id or source_index is None or target_index is None:
            return jsonify({
                'code': -1,
                'message': '参数不完整'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前商品
        sql = "SELECT id, carousel_pic_urls FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 处理 carousel_pic_urls 字段
        image_list = []
        if goods.get('carousel_pic_urls'):
            try:
                image_list = json.loads(goods['carousel_pic_urls']) if isinstance(goods['carousel_pic_urls'], str) else goods['carousel_pic_urls']
            except:
                image_list = []
        
        if not isinstance(image_list, list) or len(image_list) == 0:
            return jsonify({
                'code': -1,
                'message': '轮播图列表为空'
            }), 400
        
        if source_index < 0 or source_index >= len(image_list) or \
           target_index < 0 or target_index >= len(image_list):
            return jsonify({
                'code': -1,
                'message': '图片索引超出范围'
            }), 400
        
        # 交换位置
        image_list[source_index], image_list[target_index] = image_list[target_index], image_list[source_index]
        
        # 新增：如果交换涉及到了第1位（主图），需要同步更新所有规格图的地址
        new_main_image = image_list[0]
        sku_list = []
        if goods.get('sku_list'):
            try:
                sku_list = json.loads(goods['sku_list']) if isinstance(goods['sku_list'], str) else goods['sku_list']
            except:
                sku_list = []
        
        if isinstance(sku_list, list) and (source_index == 0 or target_index == 0):
            updated_sku_list = []
            for sku in sku_list:
                if isinstance(sku, dict):
                    updated_sku = copy.deepcopy(sku)
                    updated_sku['pic_url'] = new_main_image
                    updated_sku['pic'] = new_main_image
                    updated_sku['image'] = new_main_image
                    updated_sku_list.append(updated_sku)
                else:
                    updated_sku_list.append(sku)
            sku_list = updated_sku_list
            
            # 更新数据库（含 SKU 列表）
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s, sku_list = %s WHERE id = %s"
            cursor.execute(update_sql, (json.dumps(image_list, ensure_ascii=False), json.dumps(sku_list, ensure_ascii=False), goods_id))
        else:
            # 仅更新图片列表
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s WHERE id = %s"
            cursor.execute(update_sql, (json.dumps(image_list, ensure_ascii=False), goods_id))
        
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # 回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        return jsonify({
            'code': 0,
            'message': '图片位置已交换' + ('，回存成功' if save_result['success'] else '，但回存失败'),
            'data': {'id': goods_id, 'image_list': image_list}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


@app.route('/api/goods/remove-image', methods=['POST'])
def remove_image():
    """删除轮播图中的指定图片（切换到 v2）"""
    try:
        data = request.json
        goods_id = data.get('id')
        image_index = data.get('image_index')  # 要删除的图片索引
        
        if not goods_id or image_index is None:
            return jsonify({
                'code': -1,
                'message': '参数不完整'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前商品
        sql = "SELECT id, carousel_pic_urls, sku_list FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 处理 carousel_pic_urls 字段
        image_list = []
        if goods.get('carousel_pic_urls'):
            try:
                image_list = json.loads(goods['carousel_pic_urls']) if isinstance(goods['carousel_pic_urls'], str) else goods['carousel_pic_urls']
            except:
                image_list = []
        
        if not isinstance(image_list, list) or len(image_list) == 0:
            return jsonify({
                'code': -1,
                'message': '轮播图列表为空'
            }), 400
        
        if image_index < 0 or image_index >= len(image_list):
            return jsonify({
                'code': -1,
                'message': '图片索引超出范围'
            }), 400
        
        if len(image_list) <= 1:
            return jsonify({
                'code': -1,
                'message': '轮播图只剩一张，无法删除'
            }), 400
        
        # 删除指定索引的图片
        removed_image = image_list.pop(image_index)
        removed_image_base = removed_image.split('?')[0] if removed_image else ''
        
        # 更新主图（如果删除的是第1张，则更新为新的第1张）
        new_main_image = image_list[0] if len(image_list) > 0 else ""
        
        # 处理 sku_list
        sku_list = []
        if goods.get('sku_list'):
            try:
                sku_list = json.loads(goods['sku_list']) if isinstance(goods['sku_list'], str) else goods['sku_list']
            except:
                sku_list = []
                
        if isinstance(sku_list, list):
            updated_sku_list = []
            image_list_bases = [img.split('?')[0] for img in image_list if img]
            
            for sku in sku_list:
                if isinstance(sku, dict):
                    updated_sku = copy.deepcopy(sku)
                    
                    # 获取当前SKU的pic和image（去除参数后对比）
                    current_pic = updated_sku.get('pic', '')
                    current_image = updated_sku.get('image', '')
                    current_pic_base = current_pic.split('?')[0] if current_pic else ''
                    current_image_base = current_image.split('?')[0] if current_image else ''
                    
                    # 检查：如果删除的是主图（第1张），或者SKU的pic/image指向被删除的图片，
                    # 或者SKU的pic/image不在新的 image_list 中，都需要更新为主图
                    need_update_pic = False
                    need_update_image = False
                    
                    if image_index == 0:
                        need_update_pic = True
                        need_update_image = True
                    else:
                        if current_pic_base == removed_image_base or (current_pic_base and current_pic_base not in image_list_bases):
                            need_update_pic = True
                        if current_image_base == removed_image_base or (current_image_base and current_image_base not in image_list_bases):
                            need_update_image = True
                        
                    if need_update_pic:
                        updated_sku['pic_url'] = new_main_image
                        updated_sku['pic'] = new_main_image
                    if need_update_image:
                        updated_sku['image'] = new_main_image
                        
                    updated_sku_list.append(updated_sku)
                else:
                    updated_sku_list.append(sku)
            sku_list = updated_sku_list
            
            # 确保len、width、height字段存在（复用通用函数）
            sku_list = ensure_sku_dimensions(sku_list)
        
        # 更新数据库
        update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s, sku_list = %s WHERE id = %s"
        cursor.execute(update_sql, (json.dumps(image_list, ensure_ascii=False), json.dumps(sku_list, ensure_ascii=False), goods_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # 回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        return jsonify({
            'code': 0,
            'message': '图片已删除' + ('，回存成功' if save_result['success'] else '，但回存失败'),
            'data': {'id': goods_id, 'image_list': image_list}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


@app.route('/api/goods/re-save', methods=['POST'])
def re_save_goods():
    """重新回存商品到外部系统（用于恢复数据）"""
    try:
        data = request.json
        goods_id = data.get('id')
        
        if not goods_id:
            return jsonify({
                'code': -1,
                'message': '商品ID不能为空'
            }), 400
        
        # 使用修复后的 save_goods_to_external_api 函数回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        if save_result['success']:
            return jsonify({
                'code': 0,
                'message': '重新回存成功',
                'data': save_result
            })
        else:
            return jsonify({
                'code': -1,
                'message': f'重新回存失败: {save_result.get("error", "未知错误")}',
                'data': save_result
            }), 500
            
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'重新回存失败: {str(e)}'
        }), 500


@app.route('/api/goods/replace-main-image', methods=['POST'])
def replace_main_image():
    """更换主图（将指定图片移到第1位，并更新所有规格图）（切换到 v2）"""
    try:
        data = request.json
        goods_id = data.get('id')
        source_index = data.get('source_index')  # 要作为主图的图片索引
        
        if not goods_id or source_index is None:
            return jsonify({
                'code': -1,
                'message': '参数不完整'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前商品
        sql = "SELECT id, carousel_pic_urls, sku_list FROM temu_goods_v2 WHERE id = %s"
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if not goods:
            return jsonify({
                'code': -1,
                'message': '商品不存在'
            }), 404
        
        # 处理 carousel_pic_urls 字段
        image_list = []
        if goods.get('carousel_pic_urls'):
            try:
                image_list = json.loads(goods['carousel_pic_urls']) if isinstance(goods['carousel_pic_urls'], str) else goods['carousel_pic_urls']
            except:
                image_list = []
        
        if not isinstance(image_list, list) or len(image_list) == 0:
            return jsonify({
                'code': -1,
                'message': '轮播图列表为空'
            }), 400
        
        if source_index < 0 or source_index >= len(image_list):
            return jsonify({
                'code': -1,
                'message': '图片索引超出范围'
            }), 400
        
        # 获取新的主图URL
        new_main_image = image_list[source_index]
        
        # 将选中的图片与第1位交换
        if source_index != 0:
            image_list[0], image_list[source_index] = image_list[source_index], image_list[0]
        
        # 更新所有规格图的image和pic字段
        sku_list = []
        if goods.get('sku_list'):
            try:
                sku_list = json.loads(goods['sku_list']) if isinstance(goods['sku_list'], str) else goods['sku_list']
            except:
                sku_list = []
                
        if isinstance(sku_list, list):
            updated_sku_list = []
            for sku in sku_list:
                if isinstance(sku, dict):
                    updated_sku = copy.deepcopy(sku)
                    # 统一更新所有可能的图片字段，确保回存逻辑能抓到新图
                    updated_sku['pic_url'] = new_main_image
                    updated_sku['pic'] = new_main_image
                    updated_sku['image'] = new_main_image
                    updated_sku_list.append(updated_sku)
                else:
                    updated_sku_list.append(sku)
            sku_list = updated_sku_list
            
            # 确保关键维度字段存在
            sku_list = ensure_sku_dimensions(sku_list)
            
            # 更新数据库
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s, sku_list = %s WHERE id = %s"
            cursor.execute(update_sql, (json.dumps(image_list, ensure_ascii=False), json.dumps(sku_list, ensure_ascii=False), goods_id))
            conn.commit()
        else:
            # 只更新图片列表
            update_sql = "UPDATE temu_goods_v2 SET carousel_pic_urls = %s WHERE id = %s"
            cursor.execute(update_sql, (json.dumps(image_list, ensure_ascii=False), goods_id))
            conn.commit()
        
        cursor.close()
        conn.close()
        
        # 回存到外部系统
        save_result = save_goods_to_external_api(goods_id)
        
        return jsonify({
            'code': 0,
            'message': '主图已更换，所有规格图已更新' + ('，回存成功' if save_result['success'] else '，但回存失败'),
            'data': {
                'id': goods_id,
                'main_image': new_main_image,
                'image_list': image_list
            }
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
