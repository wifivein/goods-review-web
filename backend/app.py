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
import re
from dotenv import load_dotenv
import copy

load_dotenv()

app = Flask(__name__)
CORS(app)  # 允许跨域
# 允许大 body（如 /api/vision/describe 的 Base64 原图），避免 413
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

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


# ==========================================
# 统一查询字段定义和处理逻辑
# ==========================================

# 基础字段（列表页和详情页通用）
SQL_GOODS_BASE_FIELDS = """
    id, master_user_id as user_id, product_id as goods_id, 
    product_name as title, product_name as name, 
    carousel_pic_urls as image_list,
    create_time, update_time,
    is_publish as isupload, process_status as uploadstatus, 
    review_status,
    sale_count as soldcount,
    preprocess_tags,
    carousel_labels
"""

# 详情页额外字段
SQL_GOODS_DETAIL_FIELDS = """
    , sku_list, sku_specs as spec,
    origin_product_url as url,
    group_id, ref_product_template_id, ref_product_size_template_id,
    extcode, create_by, create_dept_id, malls,
    product_template, product_size_template, group_data as product_spec_map
"""

def _process_goods_row(row):
    """
    统一处理商品数据行：
    1. 解析 JSON 字段
    2. 提取 main_image / cover
    3. 格式化 create_time_str
    """
    if not row:
        return row
    
    # 1. JSON 字段解析
    # 列表: image_list, preprocess_tags, carousel_labels
    # 详情: 上述 + sku_list, spec, malls, product_template, product_size_template, product_spec_map
    json_fields = [
        'image_list', 'sku_list', 'spec', 'malls', 
        'product_template', 'product_size_template', 
        'product_spec_map', 'carousel_labels', 'preprocess_tags'
    ]
    
    for field in json_fields:
        if field in row:
            val = row[field]
            if val:
                try:
                    # 如果是字符串则解析，否则保持原样（已经是list/dict）
                    row[field] = json.loads(val) if isinstance(val, str) else val
                except:
                    # 解析失败时的默认值
                    # 列表类型字段
                    if field.endswith('_list') or field in ['carousel_labels', 'preprocess_tags', 'image_list']:
                        row[field] = []
                    else:
                        row[field] = {}
            else:
                # 空值的默认值
                if field.endswith('_list') or field in ['carousel_labels', 'preprocess_tags', 'image_list']:
                    row[field] = []
                else:
                    row[field] = {}

    # 2. 图片处理 (main_image, cover)
    # 依赖 image_list
    img_list = row.get('image_list')
    if isinstance(img_list, list) and len(img_list) > 0:
        row['main_image'] = img_list[0]
        row['cover'] = img_list[0]
    else:
        row['main_image'] = ""
        row['cover'] = ""

    # 3. 时间处理
    # 列表页需要 create_time_str
    if 'create_time' in row:
        ct = row['create_time']
        if isinstance(ct, datetime):
            row['create_time_str'] = ct.strftime('%Y-%m-%d %H:%M:%S')
        else:
            row['create_time_str'] = str(ct) if ct else ""

    return row



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
            timeout=30,
            proxies={}  # 不走环境代理，避免代理不可达导致整站不可用
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
            {SQL_GOODS_BASE_FIELDS}
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
            _process_goods_row(goods)
        
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


# 图片描述接口可能较慢：拉图约 30s + 智谱 API 约 60s，建议客户端超时 >= 120s
VISION_DESCRIBE_RECOMMENDED_TIMEOUT_MS = 120000


def _vision_response(data, status=200):
    """统一给 /api/vision/describe 的响应加上建议超时头，便于 n8n 等客户端设置足够长的 Timeout。"""
    resp = jsonify(data)
    resp.headers["X-Recommended-Timeout"] = str(VISION_DESCRIBE_RECOMMENDED_TIMEOUT_MS)
    return resp, status


def _parse_vision_image_inputs(data):
    """从请求体解析出图片列表，每项为 URL 或 data:image/...;base64,...。
    支持混合传图：images 数组内每项可为 url 或 base64；也支持仅 image_base64_list / image_urls 等。
    """
    # 0) 混合列表：images 中每项为 { "url": "..." } 或 { "base64": "...", "mime": "..." } 或直接字符串 URL/data URL
    images = data.get('images')
    if isinstance(images, list) and images:
        out = []
        for item in images:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip()
                if s.startswith(('http://', 'https://', 'data:image/')):
                    out.append(s)
                continue
            if isinstance(item, dict):
                if item.get('url'):
                    u = str(item['url']).strip()
                    if u.startswith(('http://', 'https://', 'data:image/')):
                        out.append(u)
                    continue
                if item.get('base64'):
                    mime = (item.get('mime') or 'image/png').strip()
                    if not mime.startswith('image/'):
                        mime = f"image/{mime}"
                    out.append(f"data:{mime};base64,{str(item['base64']).strip()}")
        if out:
            return out
    # 1) 仅 base64 列表
    base64_list = data.get('image_base64_list')
    if isinstance(base64_list, list) and base64_list:
        out = []
        for item in base64_list:
            if isinstance(item, str):
                out.append(f"data:image/png;base64,{item.strip()}")
            elif isinstance(item, dict) and item.get('base64'):
                mime = (item.get('mime') or 'image/png').strip()
                if not mime.startswith('image/'):
                    mime = f"image/{mime}"
                out.append(f"data:{mime};base64,{item['base64'].strip()}")
        if out:
            return out
    single_b64 = data.get('image_base64')
    if isinstance(single_b64, str) and single_b64.strip():
        mime = (data.get('image_base64_mime') or 'image/png').strip()
        if not mime.startswith('image/'):
            mime = f"image/{mime}"
        return [f"data:{mime};base64,{single_b64.strip()}"]
    # 2) 仅 URL 列表（N8N 等可能传 stringified 数组）
    urls = data.get('image_urls')
    if isinstance(urls, str) and urls.strip():
        try:
            urls = json.loads(urls)
        except Exception:
            urls = []
    if isinstance(urls, list):
        urls = [u for u in urls if u and str(u).strip().startswith(('http://', 'https://', 'data:image/'))]
    else:
        urls = []
    if not urls:
        single = (data.get('image_url') or '').strip()
        if single and single.startswith(('http://', 'https://', 'data:image/')):
            urls = [single]
    return urls


@app.route('/api/vision/describe', methods=['POST'])
def vision_describe():
    """调用大模型对图片进行描述/判断。
    请求体（任选一种或混合）:
      - 混合：images 数组，每项为 { "url": "..." } 或 { "base64": "...", "mime": "image/png" } 或直接字符串 URL/data URL，按顺序多图
      - 仅 URL：image_url 或 image_urls（后端会拉图，需容器能访问外网）
      - 仅 Base64：image_base64 或 image_base64_list（客户端先拉图再传，适合后端 Network unreachable）
      - prompt 可选；json_output 可选。
    拉图+智谱可能需 90s+，请将 HTTP 客户端 Timeout 设为至少 120 秒（响应头 X-Recommended-Timeout: 120000）。
    """
    try:
        from vision_api import describe_image, get_api_key
        if not get_api_key():
            return _vision_response({'code': -1, 'message': '未配置 BIGMODEL_API_KEY'}, 503)
        data = request.json or {}
        urls = _parse_vision_image_inputs(data)
        if not urls:
            return _vision_response({
                'code': -1,
                'message': '缺少图片：请传 image_url / image_urls 或 image_base64 / image_base64_list（后端无法访问外网时用 base64）'
            }, 400)
        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            prompt = '请分别描述这几张图片的内容' if len(urls) > 1 else '请描述这张图片的内容'
        json_output = data.get('json_output') is True
        success, result = describe_image(urls, prompt=prompt, response_format_json=json_output)
        if success:
            return _vision_response({'code': 0, 'message': 'success', 'data': {'content': result}})
        return _vision_response({'code': -1, 'message': str(result)}, 500)
    except Exception as e:
        return _vision_response({'code': -1, 'message': str(e)}, 500)


@app.route('/api/goods/detail/<int:goods_id>', methods=['GET'])
def get_goods_detail(goods_id):
    """获取商品详情"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 使用别名映射到前端习惯的字段名
        sql = f"""
            SELECT 
            {SQL_GOODS_BASE_FIELDS}
            {SQL_GOODS_DETAIL_FIELDS}
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
        _process_goods_row(goods)
        
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


@app.route('/api/goods/update-main-fields', methods=['POST'])
def update_goods_main_fields():
    """
    原子更新商品主要字段（供整理工作流用）。
    仅做 DB 写入，不包含业务逻辑。回存原系统由 N8N 工作流单独负责。
    """
    try:
        data = request.json
        api_id = data.get('api_id')
        if api_id is None:
            return jsonify({'code': -1, 'message': 'api_id 不能为空'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM temu_goods_v2 WHERE api_id = %s", (api_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': f'未找到 api_id={api_id} 的商品'}), 404

        goods_id = row['id']
        update_fields = []
        update_params = []

        if 'product_name' in data:
            update_fields.append('product_name = %s')
            update_params.append(data['product_name'] or '')
        if 'carousel_pic_urls' in data:
            val = data['carousel_pic_urls']
            update_fields.append('carousel_pic_urls = %s')
            update_params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
        if 'sku_list' in data:
            val = data['sku_list']
            update_fields.append('sku_list = %s')
            update_params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
        if 'preprocess_tags' in data:
            val = data['preprocess_tags']
            update_fields.append('preprocess_tags = %s')
            update_params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
        if 'carousel_labels' in data:
            val = data['carousel_labels']
            update_fields.append('carousel_labels = %s')
            update_params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
        if 'process_status' in data:
            update_fields.append('process_status = %s')
            update_params.append(data['process_status'])

        if update_fields:
            update_fields.append('update_time = NOW()')
            update_params.append(goods_id)
            cursor.execute(
                "UPDATE temu_goods_v2 SET " + ", ".join(update_fields) + " WHERE id = %s",
                update_params
            )
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {'goods_id': goods_id, 'api_id': api_id}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/goods/update-carousel-labels', methods=['POST'])
def update_goods_carousel_labels():
    """
    仅更新商品 carousel_labels（供设计图检查工作流 vision 路径回写）。
    接收 product_id，仅当该商品在新表且 carousel_labels 为空时更新。
    老表商品无记录则 0 行，不报错。
    """
    try:
        data = request.json
        product_id = data.get('product_id')
        if product_id is None or product_id == '':
            return jsonify({'code': -1, 'message': 'product_id 不能为空'}), 400

        carousel_labels = data.get('carousel_labels')
        if not isinstance(carousel_labels, list):
            return jsonify({'code': -1, 'message': 'carousel_labels 必须为数组'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        labels_json = json.dumps(carousel_labels, ensure_ascii=False)
        cursor.execute(
            """
            UPDATE temu_goods_v2 SET carousel_labels = %s, update_time = NOW()
            WHERE product_id = %s
              AND (carousel_labels IS NULL OR carousel_labels = '' OR carousel_labels = '[]')
            """,
            (labels_json, product_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {'updated': rowcount > 0, 'product_id': product_id}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


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
                    timeout=10,
                    proxies={}  # 不走环境代理
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


@app.route('/api/goods/save-label-badcase', methods=['POST'])
def save_label_badcase():
    """记录标签 badcase（打标错误样本），供后续分析和优化"""
    try:
        data = request.json
        product_id = data.get('product_id', '')
        image_url = data.get('image_url', '')
        image_index = data.get('image_index', 0)
        carousel_label = data.get('carousel_label')
        feedback_type = data.get('feedback_type', '其他')
        feedback_note = data.get('feedback_note', '')
        suggested_correct = data.get('suggested_correct', '')

        if not product_id or not image_url:
            return jsonify({'code': -1, 'message': 'product_id 和 image_url 不能为空'}), 400

        feedback_type = str(feedback_type).strip() or '其他'
        if feedback_type not in ('类型错误', '描述不准确', '打标失败误判', '其他'):
            feedback_type = '其他'
        carousel_label_json = json.dumps(carousel_label, ensure_ascii=False) if carousel_label is not None else None

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO label_badcase (product_id, image_url, image_index, carousel_label, feedback_type, feedback_note, suggested_correct)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(product_id)[:64],
                    str(image_url)[:1024],
                    int(image_index),
                    carousel_label_json,
                    feedback_type[:32],
                    str(feedback_note)[:2000] if feedback_note else '',
                    str(suggested_correct)[:2000] if suggested_correct else ''
                )
            )
            conn.commit()
            bid = cursor.lastrowid
        except pymysql.err.OperationalError as e:
            if 'doesn\'t exist' in str(e) or "doesn't exist" in str(e):
                return jsonify({'code': -1, 'message': '请先执行 sql/add_label_badcase.sql 创建 label_badcase 表'}), 500
            raise
        finally:
            cursor.close()
            conn.close()

        return jsonify({'code': 0, 'message': '已记录', 'data': {'id': bid}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


# ========== Lovart设计图审核相关API ==========

@app.route('/api/design/save-tab-mapping', methods=['POST'])
def save_tab_mapping():
    """保存Tab与商品ID的映射关系（N8N提交工作流调用）"""
    try:
        data = request.json
        tab_id = data.get('tab_id')
        tab_url = data.get('tab_url')
        tab_title = data.get('tab_title')
        product_id = data.get('product_id')
        product_name = data.get('product_name')
        category = data.get('category')
        original_image_url = data.get('original_image_url')  # 首图
        original_images_urls = data.get('original_images_urls')  # 所有原图URL数组
        
        if not tab_id or not product_id:
            return jsonify({
                'code': -1,
                'message': 'tab_id和product_id不能为空'
            }), 400
        
        # 将原图URL数组转为JSON字符串
        if isinstance(original_images_urls, list):
            original_images_urls_json = json.dumps(original_images_urls, ensure_ascii=False)
        elif isinstance(original_images_urls, str):
            original_images_urls_json = original_images_urls
        else:
            original_images_urls_json = None
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查是否已存在（根据tab_id）
        check_sql = "SELECT id FROM lovart_design_tab_mapping WHERE tab_id = %s"
        cursor.execute(check_sql, (tab_id,))
        existing = cursor.fetchone()
        
        if existing:
            # 更新
            update_sql = """
                UPDATE lovart_design_tab_mapping 
                SET tab_url = %s, tab_title = %s, product_id = %s, product_name = %s, 
                    category = %s, original_image_url = %s, original_images_urls = %s,
                    status = 'generating', updated_at = NOW()
                WHERE tab_id = %s
            """
            cursor.execute(update_sql, (
                tab_url, tab_title, product_id, product_name, category,
                original_image_url, original_images_urls_json, tab_id
            ))
        else:
            # 插入
            insert_sql = """
                INSERT INTO lovart_design_tab_mapping 
                (tab_id, tab_url, tab_title, product_id, product_name, category, 
                 original_image_url, original_images_urls, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'generating')
            """
            cursor.execute(insert_sql, (
                tab_id, tab_url, tab_title, product_id, product_name, category,
                original_image_url, original_images_urls_json
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'Tab映射保存成功',
            'data': {'tab_id': tab_id, 'product_id': product_id}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'保存失败: {str(e)}'
        }), 500


@app.route('/api/design/update-design-images-from-lovart', methods=['POST'])
def update_design_images_from_lovart():
    """N8N 从 Lovart 抓取到设计图列表后调用此接口写回；会与库中已有「本地上传」项合并，避免覆盖用户添加的设计图。
    Body: { tab_id, design_images: [ { url, title }, ... ] } 或 { tab_id, design_images_sql: "JSON 字符串" }。"""
    try:
        data = request.json
        tab_id = data.get('tab_id')
        design_images_new = data.get('design_images')
        design_images_sql = data.get('design_images_sql')
        if not tab_id:
            return jsonify({'code': -1, 'message': 'tab_id 不能为空'}), 400
        if design_images_new is None and design_images_sql is not None:
            try:
                s = design_images_sql.strip() if isinstance(design_images_sql, str) else str(design_images_sql)
                s = s.replace("''", "'")
                design_images_new = json.loads(s)
            except Exception:
                design_images_new = []
        if not isinstance(design_images_new, list):
            design_images_new = []
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, design_images FROM lovart_design_tab_mapping WHERE tab_id = %s',
            (tab_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        current = row.get('design_images')
        if current and isinstance(current, str) and current.strip():
            try:
                current = json.loads(current)
            except Exception:
                current = []
        if not isinstance(current, list):
            current = []
        local_uploads = [x for x in current if isinstance(x, dict) and (x.get('title') == '本地上传' or (x.get('url') and 'design_upload_' in str(x.get('url'))))]
        merged = list(design_images_new)
        for x in local_uploads:
            merged.append(x)
        merged_json = json.dumps(merged, ensure_ascii=False)
        cursor.execute(
            'UPDATE lovart_design_tab_mapping SET design_images = %s, updated_at = NOW() WHERE tab_id = %s',
            (merged_json, tab_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'code': 0, 'message': 'success', 'data': {'tab_id': tab_id, 'merged_count': len(merged)}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/update-completed', methods=['POST'])
def update_design_completed():
    """将记录标记为最终状态「已处理完」（completed）。仅当下载+改名+横竖版等全部做完时由调用方（如 N8N）调用。
    不再表示「生成完成」——生成中只要未在页面选定或关闭 Tab 都可能继续生成。
    支持新字段 design_images 或老字段 design_image_1/2/3；仅老字段路径会写入 status=completed。"""
    try:
        data = request.json
        tab_id = data.get('tab_id')
        design_images = data.get('design_images')  # 新字段：JSON 数组或已序列化字符串
        design_image_1_url = data.get('design_image_1_url')
        design_image_1_title = data.get('design_image_1_title')
        design_image_2_url = data.get('design_image_2_url')
        design_image_2_title = data.get('design_image_2_title')
        design_image_3_url = data.get('design_image_3_url')
        design_image_3_title = data.get('design_image_3_title')
        
        if not tab_id:
            return jsonify({
                'code': -1,
                'message': 'tab_id不能为空'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if design_images is not None:
            # 新字段：写入 design_images
            design_images_str = json.dumps(design_images) if not isinstance(design_images, str) else design_images
            update_sql = """
                UPDATE lovart_design_tab_mapping 
                SET design_images = %s, updated_at = NOW()
                WHERE tab_id = %s
            """
            cursor.execute(update_sql, (design_images_str, tab_id))
        else:
            # 老字段：写入 design_image_1/2/3，并标记为最终状态「已处理完」（completed）
            update_sql = """
                UPDATE lovart_design_tab_mapping 
                SET design_image_1_url = %s, design_image_1_title = %s,
                    design_image_2_url = %s, design_image_2_title = %s,
                    design_image_3_url = %s, design_image_3_title = %s,
                    status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE tab_id = %s
            """
            cursor.execute(update_sql, (
                design_image_1_url, design_image_1_title,
                design_image_2_url, design_image_2_title,
                design_image_3_url, design_image_3_title,
                tab_id
            ))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'code': -1,
                'message': '未找到对应的Tab映射'
            }), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': '设计图信息更新成功',
            'data': {'tab_id': tab_id}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'更新失败: {str(e)}'
        }), 500


@app.route('/api/design/pending-review', methods=['GET'])
def get_pending_review():
    """查询设计图列表（所有状态）"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询总数（所有状态）
        count_sql = """
            SELECT COUNT(*) as total 
            FROM lovart_design_tab_mapping
        """
        cursor.execute(count_sql)
        total = cursor.fetchone()['total']
        
        # 查询待审核数量（用于统计）：completed 已改为最终状态「已处理完」，不再计入待审核
        pending_count_sql = """
            SELECT COUNT(*) as pending_total 
            FROM lovart_design_tab_mapping 
            WHERE status IN ('ai_selected', 'tab_closed', 'generating')
        """
        cursor.execute(pending_count_sql)
        pending_total = cursor.fetchone()['pending_total']
        
        # 查询列表（所有状态），原图/设计图均用「排除」语义：original_excluded_indices、excluded_image_indices
        list_sql = """
            SELECT id, tab_id, tab_url, product_id, product_name, category,
                   original_image_url, original_images_urls, original_excluded_indices, original_classify_reasons,
                   design_images, excluded_image_indices, design_discard_reasons, design_check_results,
                   design_image_1_url, design_image_1_title,
                   design_image_2_url, design_image_2_title,
                   design_image_3_url, design_image_3_title,
                   ai_recommendation, ai_reason, ai_prompt_suggestion,
                   status, selected_image_index, created_at, completed_at
            FROM lovart_design_tab_mapping 
            ORDER BY (CASE WHEN status = 'generating' THEN 0 ELSE 1 END), COALESCE(completed_at, created_at) DESC
            LIMIT %s OFFSET %s
        """
        try:
            cursor.execute(list_sql, (limit, offset))
            items = cursor.fetchall()
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e) and ('original_excluded_indices' in str(e) or 'original_classify_reasons' in str(e) or 'design_discard_reasons' in str(e) or 'design_check_results' in str(e) or 'ai_prompt_suggestion' in str(e)):
                # 回退：先尝试查 original_referable_indices（旧库兼容），再尝试不查任何新列
                list_sql_with_referable = """
                    SELECT id, tab_id, tab_url, product_id, product_name, category,
                           original_image_url, original_images_urls, original_referable_indices,
                           design_images, excluded_image_indices, design_discard_reasons,
                           design_image_1_url, design_image_1_title,
                           design_image_2_url, design_image_2_title,
                           design_image_3_url, design_image_3_title,
                           ai_recommendation, ai_reason,
                           status, selected_image_index, created_at, completed_at
                    FROM lovart_design_tab_mapping 
                    ORDER BY (CASE WHEN status = 'generating' THEN 0 ELSE 1 END), COALESCE(completed_at, created_at) DESC
                    LIMIT %s OFFSET %s
                """
                list_sql_minimal = """
                    SELECT id, tab_id, tab_url, product_id, product_name, category,
                           original_image_url, original_images_urls,
                           design_images, excluded_image_indices,
                           design_image_1_url, design_image_1_title,
                           design_image_2_url, design_image_2_title,
                           design_image_3_url, design_image_3_title,
                           ai_recommendation, ai_reason,
                           status, selected_image_index, created_at, completed_at
                    FROM lovart_design_tab_mapping 
                    ORDER BY (CASE WHEN status = 'generating' THEN 0 ELSE 1 END), COALESCE(completed_at, created_at) DESC
                    LIMIT %s OFFSET %s
                """
                try:
                    cursor.execute(list_sql_with_referable, (limit, offset))
                    items = cursor.fetchall()
                    for it in items:
                        it['original_excluded_indices'] = None  # 下方循环从 original_referable_indices 推导
                        it['original_classify_reasons'] = []
                        it['design_discard_reasons'] = []
                        it['design_check_results'] = []
                        it['ai_prompt_suggestion'] = None
                except pymysql.err.OperationalError as e2:
                    if 'Unknown column' in str(e2):
                        cursor.execute(list_sql_minimal, (limit, offset))
                        items = cursor.fetchall()
                        for it in items:
                            it['original_excluded_indices'] = []
                            it['original_classify_reasons'] = []
                            it['design_discard_reasons'] = []
                            it['design_check_results'] = []
                            it['ai_prompt_suggestion'] = None
                    else:
                        raise
            else:
                raise
        
        # 处理原图URL数组、design_images、excluded_image_indices（保持原样，前端优先用新字段再回退老字段）
        for item in items:
            if item.get('original_images_urls'):
                try:
                    item['original_images_urls'] = json.loads(item['original_images_urls'])
                except:
                    item['original_images_urls'] = []
            else:
                item['original_images_urls'] = []
            # design_images 若为字符串则保持，前端会 JSON.parse；若为 None 则前端走老字段
            if item.get('design_images') is not None and isinstance(item['design_images'], str):
                try:
                    item['design_images'] = json.loads(item['design_images']) if item['design_images'].strip() else []
                except Exception:
                    item['design_images'] = []
            # 排除的设计图索引（JSON 数组，如 [0,2]）
            if item.get('excluded_image_indices') is not None and isinstance(item['excluded_image_indices'], str):
                try:
                    item['excluded_image_indices'] = json.loads(item['excluded_image_indices']) if item['excluded_image_indices'].strip() else []
                except Exception:
                    item['excluded_image_indices'] = []
            else:
                item['excluded_image_indices'] = item.get('excluded_image_indices') or []
            # 原图排除下标（与设计图 excluded_image_indices 语义一致）；兼容旧字段 original_referable_indices
            _urls_len = len(item.get('original_images_urls') or [])
            if item.get('original_excluded_indices') is not None and isinstance(item.get('original_excluded_indices'), str):
                try:
                    item['original_excluded_indices'] = json.loads(item['original_excluded_indices']) if item['original_excluded_indices'].strip() else []
                except Exception:
                    item['original_excluded_indices'] = []
            elif isinstance(item.get('original_excluded_indices'), list):
                item['original_excluded_indices'] = item['original_excluded_indices']
            else:
                # 兼容旧库 original_referable_indices：未设置或空 = 默认不排除任何原图
                referable_raw = item.get('original_referable_indices')
                if isinstance(referable_raw, str) and referable_raw:
                    try:
                        referable = json.loads(referable_raw)
                    except Exception:
                        referable = []
                else:
                    referable = referable_raw if isinstance(referable_raw, list) else []
                if referable is None or (isinstance(referable, list) and len(referable) == 0):
                    item['original_excluded_indices'] = []
                else:
                    item['original_excluded_indices'] = [i for i in range(_urls_len) if i not in referable]
            if 'original_referable_indices' in item:
                del item['original_referable_indices']
            # 原图预检结果（JSON 数组 [{index, referable, reason}]），供前端悬停显示
            if item.get('original_classify_reasons') is not None and isinstance(item.get('original_classify_reasons'), str):
                try:
                    item['original_classify_reasons'] = json.loads(item['original_classify_reasons']) if item['original_classify_reasons'].strip() else []
                except Exception:
                    item['original_classify_reasons'] = []
            else:
                item['original_classify_reasons'] = item.get('original_classify_reasons') if isinstance(item.get('original_classify_reasons'), list) else []
            # 设计图一票否决原因（JSON 数组 [{index, reason}]）
            if item.get('design_discard_reasons') is not None and isinstance(item.get('design_discard_reasons'), str):
                try:
                    item['design_discard_reasons'] = json.loads(item['design_discard_reasons']) if item['design_discard_reasons'].strip() else []
                except Exception:
                    item['design_discard_reasons'] = []
            else:
                item['design_discard_reasons'] = item.get('design_discard_reasons') if isinstance(item.get('design_discard_reasons'), list) else []
            # 设计图基础检测完整结果（每张图 pass + reason）
            if item.get('design_check_results') is not None and isinstance(item.get('design_check_results'), str):
                try:
                    item['design_check_results'] = json.loads(item['design_check_results']) if item['design_check_results'].strip() else []
                except Exception:
                    item['design_check_results'] = []
            else:
                item['design_check_results'] = item.get('design_check_results') if isinstance(item.get('design_check_results'), list) else []
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {
                'list': items,
                'total': total,
                'pending_total': pending_total,
                'page': page,
                'limit': limit
            }
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/design/debug-design-data', methods=['GET'])
def debug_design_data():
    """排查设计图不显示：返回最近几条的 design_images / design_image_*_url 原始值，用于区分是库没存还是前端没展示"""
    try:
        limit = min(int(request.args.get('limit', 3)), 10)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, tab_id, status,
                       design_images, design_image_1_url, design_image_2_url, design_image_3_url,
                       design_discard_reasons, ai_reason
                FROM lovart_design_tab_mapping
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            # 转为可 JSON 序列化的结构（Decimal/datetime 等）
            out = []
            for r in rows:
                out.append({
                    'id': r.get('id'),
                    'tab_id': r.get('tab_id'),
                    'status': r.get('status'),
                    'design_images_raw': r.get('design_images'),
                    'design_image_1_url': r.get('design_image_1_url'),
                    'design_image_2_url': r.get('design_image_2_url'),
                    'design_image_3_url': r.get('design_image_3_url'),
                    'design_discard_reasons_raw': r.get('design_discard_reasons'),
                    'ai_reason': r.get('ai_reason'),
                })
            cursor.close()
            conn.close()
            return jsonify({'code': 0, 'message': 'success', 'data': {'rows': out}})
        except pymysql.err.OperationalError as e:
            cursor.close()
            conn.close()
            err = str(e)
            if 'Unknown column' in err:
                return jsonify({
                    'code': -1,
                    'message': f'表缺少列，请执行迁移: {err}',
                    'data': {'hint': 'design_images 或 design_discard_reasons 可能未添加，见 chrome_extension/sql/add_lovart_referable_and_discard.sql 等'}
                }), 400
            raise
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/set-excluded', methods=['POST'])
def set_design_excluded():
    """持久化「排除」的设计图索引（设计图审核页用）"""
    try:
        data = request.json
        mapping_id = data.get('id')
        excluded_image_indices = data.get('excluded_image_indices')
        if mapping_id is None:
            return jsonify({'code': -1, 'message': 'id 不能为空'}), 400
        if not isinstance(excluded_image_indices, list):
            excluded_image_indices = []
        excluded_image_indices = [int(x) for x in excluded_image_indices if isinstance(x, (int, float)) and int(x) >= 0]
        excluded_json = json.dumps(excluded_image_indices)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE lovart_design_tab_mapping SET excluded_image_indices = %s, updated_at = NOW() WHERE id = %s",
            (excluded_json, mapping_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if rowcount == 0:
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        return jsonify({'code': 0, 'message': 'success', 'data': {'excluded_image_indices': excluded_image_indices}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/set-excluded-originals', methods=['POST'])
def set_excluded_originals():
    """持久化「排除」的原图下标（与设计图 excluded_image_indices 语义一致）"""
    try:
        data = request.json
        mapping_id = data.get('id')
        excluded_indices = data.get('excluded_indices')
        if mapping_id is None:
            return jsonify({'code': -1, 'message': 'id 不能为空'}), 400
        if isinstance(excluded_indices, str) and excluded_indices.strip():
            try:
                excluded_indices = json.loads(excluded_indices)
            except Exception:
                excluded_indices = []
        if not isinstance(excluded_indices, list):
            excluded_indices = []
        excluded_indices = [int(x) for x in excluded_indices if isinstance(x, (int, float)) and int(x) >= 0]
        excluded_json = json.dumps(excluded_indices)
        # 可选：原图预检结果 [{index, referable, reason}]，供前端悬停显示
        classify_reasons = data.get('original_classify_reasons')
        if isinstance(classify_reasons, str) and classify_reasons.strip():
            try:
                classify_reasons = json.loads(classify_reasons)
            except Exception:
                classify_reasons = None
        if not isinstance(classify_reasons, list):
            classify_reasons = []
        classify_reasons = [x for x in classify_reasons if isinstance(x, dict) and 'index' in x]
        classify_json = json.dumps(classify_reasons, ensure_ascii=False)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE lovart_design_tab_mapping SET original_excluded_indices = %s, original_classify_reasons = %s, updated_at = NOW() WHERE id = %s",
                (excluded_json, classify_json, mapping_id)
            )
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e) and 'original_classify_reasons' in str(e):
                cursor.execute(
                    "UPDATE lovart_design_tab_mapping SET original_excluded_indices = %s, updated_at = NOW() WHERE id = %s",
                    (excluded_json, mapping_id)
                )
            else:
                raise
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if rowcount == 0:
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        return jsonify({'code': 0, 'message': 'success', 'data': {'excluded_indices': excluded_indices}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


# ---------- AI 推荐配置（页面可修改提示词）-----------
DESIGN_AI_RECOMMEND_PROMPT_KEY = 'design_ai_recommend_prompt'
DEFAULT_AI_RECOMMEND_PROMPT = (
    '你看到的前 {{original_count}} 张是商品原图（参考），后 {{design_count}} 张是设计图（候选）。'
    '请根据原图对每张设计图做还原度评分（0-1），并严格按 JSON 输出：'
    '{"scores":[{"index":1,"score":0.85,"reason":"..."},...],"best_index":1,"overall_reason":"...","need_regenerate":false,"prompt_suggestion":null}。'
    'index 为设计图序号（1 到 {{design_count}}）。若所有设计图还原度都低于 0.6，则 need_regenerate 为 true，prompt_suggestion 给出重新生成的具体提示词建议（一句话）。只输出 JSON，不要其他文字。'
)


@app.route('/api/design/config/prompt', methods=['GET'])
def get_design_ai_recommend_prompt():
    """获取 AI 推荐提示词（页面配置用）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT cvalue FROM goods_review_config WHERE ckey = %s",
                (DESIGN_AI_RECOMMEND_PROMPT_KEY,)
            )
            row = cursor.fetchone()
            prompt = (row['cvalue'] or '').strip() if row and row.get('cvalue') else DEFAULT_AI_RECOMMEND_PROMPT
        except pymysql.err.OperationalError as e:
            if 'does not exist' in str(e).lower() or 'Unknown table' in str(e):
                prompt = DEFAULT_AI_RECOMMEND_PROMPT
            else:
                raise
        cursor.close()
        conn.close()
        return jsonify({'code': 0, 'message': 'success', 'data': {'prompt': prompt}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/config/prompt', methods=['PUT', 'POST'])
def set_design_ai_recommend_prompt():
    """保存 AI 推荐提示词（页面配置用）"""
    try:
        data = request.json or {}
        prompt = (data.get('prompt') or '').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO goods_review_config (ckey, cvalue) VALUES (%s, %s) ON DUPLICATE KEY UPDATE cvalue = %s",
            (DESIGN_AI_RECOMMEND_PROMPT_KEY, prompt, prompt)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'code': 0, 'message': 'success', 'data': {'prompt': prompt}})
    except pymysql.err.OperationalError as e:
        if 'does not exist' in str(e).lower() or 'Unknown table' in str(e):
            return jsonify({'code': -1, 'message': '请先执行 sql/add_goods_review_config.sql 创建配置表'}), 400
        raise
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/ai-recommend', methods=['POST'])
def design_ai_recommend():
    """对一条记录执行 AI 推荐：未排除原图 + 未排除且通过基础检测的设计图，综合评分选最优或建议重新生成。"""
    try:
        data = request.json or {}
        mapping_id = data.get('id')
        if not mapping_id:
            return jsonify({'code': -1, 'message': 'id 不能为空'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, original_images_urls, original_excluded_indices,
                          design_images, design_image_1_url, design_image_2_url, design_image_3_url,
                          excluded_image_indices, design_check_results, design_images_uploaded_urls,
                          ai_recommendation, ai_reason
                   FROM lovart_design_tab_mapping WHERE id = %s""",
                (mapping_id,)
            )
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e) and 'design_images_uploaded_urls' in str(e):
                cursor.execute(
                    """SELECT id, original_images_urls, original_excluded_indices,
                              design_images, design_image_1_url, design_image_2_url, design_image_3_url,
                              excluded_image_indices, design_check_results,
                              ai_recommendation, ai_reason
                       FROM lovart_design_tab_mapping WHERE id = %s""",
                    (mapping_id,)
                )
            else:
                raise
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404

        # 未排除的原图 URL 列表
        urls_raw = row.get('original_images_urls')
        if urls_raw and isinstance(urls_raw, str):
            try:
                urls_raw = json.loads(urls_raw) if urls_raw.strip() else []
            except Exception:
                urls_raw = []
        if not isinstance(urls_raw, list):
            urls_raw = []
        excluded_originals = row.get('original_excluded_indices')
        if excluded_originals and isinstance(excluded_originals, str):
            try:
                excluded_originals = json.loads(excluded_originals) if excluded_originals.strip() else []
            except Exception:
                excluded_originals = []
        if not isinstance(excluded_originals, list):
            excluded_originals = []
        original_urls = [u for i, u in enumerate(urls_raw) if u and i not in excluded_originals]
        if not original_urls:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': '没有可用的商品原图（请先添加或取消排除）'}), 400

        # 上传后的设计图 URL（N8N 写回，服务端可拉；优先用此拉图）
        uploaded_url_map = {}
        uploaded_raw = row.get('design_images_uploaded_urls')
        if uploaded_raw and isinstance(uploaded_raw, str):
            try:
                uploaded_list = json.loads(uploaded_raw) if uploaded_raw.strip() else []
            except Exception:
                uploaded_list = []
        else:
            uploaded_list = uploaded_raw if isinstance(uploaded_raw, list) else []
        for x in uploaded_list:
            if isinstance(x, dict) and x.get('url') and x.get('index') is not None:
                uploaded_url_map[int(x['index'])] = str(x['url']).strip()

        # 未排除且通过基础检测的设计图：(index, url)，url 优先用上传后的
        design_list = []
        dm = row.get('design_images')
        if dm and isinstance(dm, str):
            try:
                dm = json.loads(dm) if dm.strip() else []
            except Exception:
                dm = []
        if isinstance(dm, list) and len(dm) > 0:
            for i, item in enumerate(dm):
                idx_1based = i + 1
                url = item.get('url') if isinstance(item, dict) else (item if isinstance(item, str) else '')
                url = uploaded_url_map.get(idx_1based) or url
                if url:
                    design_list.append((idx_1based, url))
        else:
            for i in (1, 2, 3):
                u = uploaded_url_map.get(i) or row.get(f'design_image_{i}_url')
                if u:
                    design_list.append((i, u))
        excluded_designs = row.get('excluded_image_indices') or []
        if isinstance(excluded_designs, str):
            try:
                excluded_designs = json.loads(excluded_designs) if excluded_designs.strip() else []
            except Exception:
                excluded_designs = []
        check_results = row.get('design_check_results')
        if check_results and isinstance(check_results, str):
            try:
                check_results = json.loads(check_results) if check_results.strip() else []
            except Exception:
                check_results = []
        # 只保留：未排除 且 (有 design_check_results 时须 pass=True)
        design_candidates = []
        for idx_1based, url in design_list:
            if idx_1based in excluded_designs:
                continue
            if isinstance(check_results, list) and len(check_results) > 0:
                entry = next((r for r in check_results if r and int(r.get('index', -1)) == idx_1based), None)
                if entry and entry.get('pass') is not True:
                    continue
            design_candidates.append((idx_1based, url))

        if not design_candidates:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': '没有可用的设计图（请先取消排除或完成基础检测）'}), 400

        # 加载配置：提示词、API Key、阈值（配置表优先，缺省用环境变量）
        def _get_config(key: str, default: str = "") -> str:
            try:
                cursor.execute("SELECT cvalue FROM goods_review_config WHERE ckey = %s", (key,))
                row = cursor.fetchone()
                v = (row['cvalue'] or '').strip() if row and row.get('cvalue') else default
                return v
            except Exception:
                return default

        prompt_tpl = _get_config(DESIGN_AI_RECOMMEND_PROMPT_KEY, DEFAULT_AI_RECOMMEND_PROMPT)
        prompt_tpl = prompt_tpl.replace('{{original_count}}', str(len(original_urls)))
        prompt_tpl = prompt_tpl.replace('{{design_count}}', str(len(design_candidates)))

        api_key = _get_config('bigmodel_api_key', '').strip() or os.getenv('BIGMODEL_API_KEY') or os.getenv('GLM_API_KEY') or ''
        if not api_key:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': '未配置 BIGMODEL_API_KEY（配置表或环境变量）'}), 503

        threshold_str = _get_config('design_ai_recommend_threshold', '').strip() or os.getenv('AI_RECOMMEND_THRESHOLD', '0.6')
        try:
            threshold = float(threshold_str)
        except (TypeError, ValueError):
            threshold = 0.6

        # 图片顺序：先原图，再设计图（按 index 1,2,3）
        image_urls = list(original_urls) + [u for _, u in sorted(design_candidates, key=lambda x: x[0])]

        from vision_api import describe_image
        success, result = describe_image(image_urls, prompt=prompt_tpl, response_format_json=True, api_key=api_key)
        if not success:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': str(result)}), 500

        try:
            if isinstance(result, str):
                out = json.loads(result)
            else:
                out = result
        except Exception as e:
            cursor.close()
            conn.close()
            return jsonify({'code': -1, 'message': f'模型输出非 JSON: {result[:200]}'}), 500

        scores = out.get('scores') or []
        best_index = out.get('best_index')
        overall_reason = (out.get('overall_reason') or '').strip()
        need_regenerate = out.get('need_regenerate') is True
        prompt_suggestion = (out.get('prompt_suggestion') or '').strip() or None

        max_score = 0.0
        if isinstance(scores, list):
            for s in scores:
                if isinstance(s, dict) and 'score' in s:
                    try:
                        max_score = max(max_score, float(s.get('score', 0)))
                    except (TypeError, ValueError):
                        pass
        if not need_regenerate and max_score < threshold:
            need_regenerate = True
            if not prompt_suggestion:
                prompt_suggestion = f'最高还原度 {max_score:.2f} 低于阈值 {threshold}，建议重新生成并明确风格要求。'

        # 写回 DB（兼容无 ai_prompt_suggestion 列）
        if need_regenerate:
            ai_rec = None
            ai_reason_val = None
            ai_prompt_val = prompt_suggestion
        else:
            ai_rec = int(best_index) if best_index is not None else None
            if ai_rec and ai_rec not in [r[0] for r in design_candidates]:
                ai_rec = design_candidates[0][0] if design_candidates else None
            ai_reason_val = overall_reason or None
            ai_prompt_val = None

        try:
            cursor.execute(
                """UPDATE lovart_design_tab_mapping
                   SET ai_recommendation = %s, ai_reason = %s, ai_prompt_suggestion = %s, updated_at = NOW()
                   WHERE id = %s""",
                (ai_rec, ai_reason_val, ai_prompt_val, mapping_id)
            )
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e) and 'ai_prompt_suggestion' in str(e):
                cursor.execute(
                    """UPDATE lovart_design_tab_mapping
                       SET ai_recommendation = %s, ai_reason = %s, updated_at = NOW()
                       WHERE id = %s""",
                    (ai_rec, ai_reason_val, mapping_id)
                )
                ai_prompt_val = prompt_suggestion if need_regenerate else None
            else:
                raise
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {
                'recommended_index': ai_rec,
                'ai_reason': ai_reason_val,
                'need_regenerate': need_regenerate,
                'prompt_suggestion': ai_prompt_val or prompt_suggestion
            }
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/reset-design-check', methods=['POST'])
def reset_design_check():
    """重置该条记录的设计图预检结果：清空 design_check_results、design_discard_reasons、design_images_uploaded_urls；
    并从排除列表中移除因预检而加入的排除项，下次 N8N 会对所有设计图重新预检。"""
    try:
        data = request.json
        mapping_id = data.get('id')
        if not mapping_id:
            return jsonify({'code': -1, 'message': 'id 不能为空'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()
        discarded_indices = []
        current_excluded = []
        try:
            cursor.execute(
                "SELECT design_check_results, excluded_image_indices FROM lovart_design_tab_mapping WHERE id = %s",
                (mapping_id,)
            )
            row = cursor.fetchone()
            if row:
                dc = row.get('design_check_results')
                if dc and isinstance(dc, str) and dc.strip():
                    try:
                        arr = json.loads(dc)
                        if isinstance(arr, list):
                            discarded_indices = [int(x['index']) for x in arr if isinstance(x, dict) and x.get('pass') is not True and x.get('index') is not None]
                    except Exception:
                        pass
                ex = row.get('excluded_image_indices')
                if ex and isinstance(ex, str) and ex.strip():
                    try:
                        current_excluded = json.loads(ex) if isinstance(ex, str) else ex
                        if isinstance(current_excluded, list):
                            current_excluded = [int(x) for x in current_excluded if isinstance(x, (int, float))]
                        else:
                            current_excluded = []
                    except Exception:
                        current_excluded = []
                elif isinstance(ex, list):
                    current_excluded = [int(x) for x in ex if isinstance(x, (int, float))]
        except pymysql.err.OperationalError:
            pass
        new_excluded = sorted(set(current_excluded) - set(discarded_indices))
        excluded_json = json.dumps(new_excluded, ensure_ascii=False)
        try:
            cursor.execute(
                """UPDATE lovart_design_tab_mapping 
                   SET design_discard_reasons = NULL, design_check_results = NULL, design_images_uploaded_urls = NULL, excluded_image_indices = %s, updated_at = NOW() 
                   WHERE id = %s""",
                (excluded_json, mapping_id)
            )
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e):
                cursor.execute(
                    "UPDATE lovart_design_tab_mapping SET design_discard_reasons = NULL, design_check_results = NULL, design_images_uploaded_urls = NULL, updated_at = NOW() WHERE id = %s",
                    (mapping_id,)
                )
            else:
                raise
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if rowcount == 0:
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        return jsonify({'code': 0, 'message': '已重置预检结果，预检导致的排除已清除，下次 N8N 检查会对所有设计图重新预检', 'data': {'id': mapping_id}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/set-discard-reasons', methods=['POST'])
def set_design_discard_reasons():
    """持久化设计图基础检测结果：支持完整结果 design_check_results（每张图 pass+reason），或仅 design_discard_reasons（兼容旧 N8N）"""
    try:
        data = request.json
        mapping_id = data.get('id')
        design_check_results = data.get('design_check_results')  # 完整结果 [{index, pass, reason}, ...]，index 为 1-based
        design_discard_reasons = data.get('design_discard_reasons')
        if mapping_id is None:
            return jsonify({'code': -1, 'message': 'id 不能为空'}), 400
        # 若传了完整结果，从中推导废弃列表并写两列；可同时传 design_images_uploaded 写回上传后 URL（供 AI 推荐拉图）
        if isinstance(design_check_results, list) and len(design_check_results) > 0:
            normalized_full = []
            for x in design_check_results:
                if not isinstance(x, dict) or 'index' not in x:
                    continue
                idx = int(x['index']) if isinstance(x.get('index'), (int, float)) else None
                if idx is None or idx < 0:
                    continue
                pass_val = x.get('pass') is True
                reason = str(x.get('reason', '')).strip() or ('通过基础检查' if pass_val else '未通过基础检查')
                normalized_full.append({'index': idx, 'pass': pass_val, 'reason': reason})
            discard_from_full = [{'index': x['index'], 'reason': x['reason']} for x in normalized_full if x.get('pass') is not True]
            check_json = json.dumps(normalized_full, ensure_ascii=False)
            discard_json = json.dumps(discard_from_full, ensure_ascii=False)
            # 优先使用 newly_discarded_indices：仅合并本次新排除的，不覆盖用户已取消排除的
            newly_discarded = data.get('newly_discarded_indices')
            if isinstance(newly_discarded, list) and len(newly_discarded) > 0:
                to_add = [int(x) for x in newly_discarded if isinstance(x, (int, float)) and int(x) >= 0]
            else:
                to_add = [int(x['index']) for x in discard_from_full if x.get('index') is not None]
            design_images_uploaded = data.get('design_images_uploaded')
            uploaded_json = None
            if isinstance(design_images_uploaded, list) and len(design_images_uploaded) > 0:
                normalized_uploaded = []
                for x in design_images_uploaded:
                    if isinstance(x, dict) and x.get('index') is not None and x.get('url'):
                        idx = int(x['index']) if isinstance(x.get('index'), (int, float)) else None
                        if idx is not None and idx >= 0:
                            normalized_uploaded.append({'index': idx, 'url': str(x['url']).strip()})
                if normalized_uploaded:
                    uploaded_json = json.dumps(normalized_uploaded, ensure_ascii=False)
            conn = get_db_connection()
            cursor = conn.cursor()
            excluded_json = None
            if to_add:
                cursor.execute("SELECT excluded_image_indices FROM lovart_design_tab_mapping WHERE id = %s", (mapping_id,))
                row = cursor.fetchone()
                current_excluded = []
                if row and row.get('excluded_image_indices'):
                    raw = row['excluded_image_indices']
                    try:
                        current_excluded = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
                    except Exception:
                        pass
                current_excluded = [int(x) for x in current_excluded if isinstance(x, (int, float))]
                merged_excluded = sorted(set(current_excluded) | set(to_add))
                excluded_json = json.dumps(merged_excluded, ensure_ascii=False)
            try:
                if uploaded_json and excluded_json is not None:
                    cursor.execute(
                        "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, design_images_uploaded_urls = %s, excluded_image_indices = %s, updated_at = NOW() WHERE id = %s",
                        (discard_json, check_json, uploaded_json, excluded_json, mapping_id)
                    )
                elif uploaded_json:
                    cursor.execute(
                        "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, design_images_uploaded_urls = %s, updated_at = NOW() WHERE id = %s",
                        (discard_json, check_json, uploaded_json, mapping_id)
                    )
                elif excluded_json is not None:
                    cursor.execute(
                        "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, excluded_image_indices = %s, updated_at = NOW() WHERE id = %s",
                        (discard_json, check_json, excluded_json, mapping_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, updated_at = NOW() WHERE id = %s",
                        (discard_json, check_json, mapping_id)
                    )
            except pymysql.err.OperationalError as e:
                err_str = str(e)
                if 'Unknown column' in err_str and 'design_check_results' in err_str:
                    cursor.execute(
                        "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, updated_at = NOW() WHERE id = %s",
                        (discard_json, mapping_id)
                    )
                elif 'Unknown column' in err_str and 'design_images_uploaded_urls' in err_str:
                    if excluded_json is not None:
                        cursor.execute(
                            "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, excluded_image_indices = %s, updated_at = NOW() WHERE id = %s",
                            (discard_json, check_json, excluded_json, mapping_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, updated_at = NOW() WHERE id = %s",
                            (discard_json, check_json, mapping_id)
                        )
                elif 'Unknown column' in err_str and 'excluded_image_indices' in err_str:
                    if uploaded_json:
                        cursor.execute(
                            "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, design_images_uploaded_urls = %s, updated_at = NOW() WHERE id = %s",
                            (discard_json, check_json, uploaded_json, mapping_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, design_check_results = %s, updated_at = NOW() WHERE id = %s",
                            (discard_json, check_json, mapping_id)
                        )
                else:
                    raise
            rowcount = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            if rowcount == 0:
                return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
            return jsonify({'code': 0, 'message': 'success', 'data': {'design_check_results': normalized_full, 'design_discard_reasons': discard_from_full}})
        # 仅传 design_discard_reasons（兼容旧 N8N）
        if not isinstance(design_discard_reasons, list):
            design_discard_reasons = []
        normalized = []
        for x in design_discard_reasons:
            if isinstance(x, dict) and 'index' in x:
                idx = int(x['index']) if isinstance(x.get('index'), (int, float)) else None
                if idx is not None and idx >= 0:
                    normalized.append({'index': idx, 'reason': str(x.get('reason', '')).strip() or '未通过基础检查'})
        discard_json = json.dumps(normalized, ensure_ascii=False)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE lovart_design_tab_mapping SET design_discard_reasons = %s, updated_at = NOW() WHERE id = %s",
            (discard_json, mapping_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if rowcount == 0:
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        return jsonify({'code': 0, 'message': 'success', 'data': {'design_discard_reasons': normalized}})
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


# 设计图临时目录：大模型检测完成后可删临时图（N8N 上传到 /opt/images 的 design_*.png）
# 本地上传的设计图命名为 design_upload_*，不参与 delete-temp-images 删除
DESIGN_IMAGES_DIR = os.getenv('DESIGN_IMAGES_DIR', '/opt/images')
DESIGN_TEMP_FILENAME_PATTERN = re.compile(r'^design_\d+_\d+\.(png|jpg|jpeg|webp)$', re.IGNORECASE)
DESIGN_UPLOAD_EXT = re.compile(r'^\.(png|jpg|jpeg|webp)$', re.IGNORECASE)


@app.route('/api/design/delete-temp-images', methods=['POST'])
def delete_design_temp_images():
    """删除设计图检测用临时图（大模型检测拿到结果后由 N8N 调用）。只允许删除 design_*.png 等安全文件名。"""
    try:
        data = request.json or {}
        filenames = data.get('filenames')
        if not isinstance(filenames, list):
            filenames = []
        base_dir = os.path.abspath(DESIGN_IMAGES_DIR)
        if not os.path.isdir(base_dir):
            return jsonify({'code': 0, 'message': 'success', 'data': {'deleted': [], 'failed': [], 'skipped': []}})
        deleted = []
        failed = []
        skipped = []
        for name in filenames:
            if not name or not isinstance(name, str):
                skipped.append(name)
                continue
            name = name.strip()
            if not DESIGN_TEMP_FILENAME_PATTERN.match(name):
                skipped.append(name)
                continue
            path = os.path.abspath(os.path.join(base_dir, name))
            if not path.startswith(base_dir) or os.path.dirname(path) != base_dir:
                skipped.append(name)
                continue
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    deleted.append(name)
                else:
                    skipped.append(name)
            except Exception as e:
                failed.append({'filename': name, 'error': str(e)})
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': {'deleted': deleted, 'failed': failed, 'skipped': skipped}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': str(e)}), 500


@app.route('/api/design/approve', methods=['POST'])
def approve_design():
    """用户选择设计图并触发下载转换工作流"""
    try:
        data = request.json
        mapping_id = data.get('id')  # lovart_design_tab_mapping的id
        selected_image_index = data.get('selected_image_index')  # 1, 2, 或 3
        
        if not mapping_id or not selected_image_index:
            return jsonify({
                'code': -1,
                'message': 'id和selected_image_index不能为空'
            }), 400
        
        if not isinstance(selected_image_index, int) or selected_image_index < 1:
            return jsonify({
                'code': -1,
                'message': 'selected_image_index必须是大于0的整数'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询映射信息（含新字段 design_images），generating/tab_closed/ai_selected 可选定（completed 已为最终状态不可再操作）
        select_sql = """
            SELECT tab_id, product_id, product_name, category,
                   design_images,
                   design_image_1_url, design_image_2_url, design_image_3_url
            FROM lovart_design_tab_mapping 
            WHERE id = %s AND status IN ('ai_selected', 'tab_closed', 'generating')
        """
        cursor.execute(select_sql, (mapping_id,))
        mapping = cursor.fetchone()
        
        if not mapping:
            cursor.close()
            conn.close()
            return jsonify({
                'code': -1,
                'message': '未找到对应的设计图记录或状态不正确'
            }), 404
        
        # 获取选中的设计图URL：优先从 design_images 按索引取，否则回退老字段
        selected_image_url = None
        design_images = mapping.get('design_images')
        if design_images:
            if isinstance(design_images, str):
                try:
                    design_images = json.loads(design_images) if design_images.strip() else []
                except Exception:
                    design_images = []
            if isinstance(design_images, list) and len(design_images) >= selected_image_index:
                idx = selected_image_index - 1
                chosen = design_images[idx] if isinstance(design_images[idx], dict) else {}
                selected_image_url = chosen.get('url') or (design_images[idx] if isinstance(design_images[idx], str) else None)
        if not selected_image_url and selected_image_index <= 3:
            image_url_field = f'design_image_{selected_image_index}_url'
            selected_image_url = mapping.get(image_url_field)
        
        if not selected_image_url:
            cursor.close()
            conn.close()
            return jsonify({
                'code': -1,
                'message': f'未找到第{selected_image_index}张设计图URL'
            }), 404
        
        # 更新数据库状态
        update_sql = """
            UPDATE lovart_design_tab_mapping 
            SET selected_image_index = %s, selected_image_url = %s,
                status = 'approved', approved_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """
        cursor.execute(update_sql, (selected_image_index, selected_image_url, mapping_id))
        conn.commit()
        cursor.close()
        conn.close()
        
        # TODO: 触发N8N下载转换工作流
        # 这里需要调用N8N的webhook或API来触发工作流
        # 暂时先返回成功，后续实现N8N触发逻辑
        
        return jsonify({
            'code': 0,
            'message': '设计图已采纳，下载转换工作流已触发',
            'data': {
                'id': mapping_id,
                'selected_image_index': selected_image_index,
                'selected_image_url': selected_image_url,
                'product_id': mapping['product_id']
            }
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


@app.route('/api/design/fail', methods=['POST'])
def fail_design():
    """放弃选择，标记为需人工调整（状态改为failed）"""
    try:
        data = request.json
        mapping_id = data.get('id')
        
        if not mapping_id:
            return jsonify({
                'code': -1,
                'message': 'id不能为空'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        update_sql = """
            UPDATE lovart_design_tab_mapping 
            SET status = 'failed', updated_at = NOW()
            WHERE id = %s AND status IN ('ai_selected', 'tab_closed', 'generating')
        """
        cursor.execute(update_sql, (mapping_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'code': -1,
                'message': '未找到对应的记录或状态不正确'
            }), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': '已标记为需人工调整',
            'data': {'id': mapping_id}
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'操作失败: {str(e)}'
        }), 500


@app.route('/api/design/switch-tab', methods=['POST'])
def switch_design_tab():
    """更换待审核记录的 Tab（新 Tab 的 tab_id 由前端经扩展解析 URL 后传入）"""
    try:
        data = request.json
        mapping_id = data.get('id')
        tab_id = data.get('tab_id')
        tab_url = data.get('tab_url')
        
        if not mapping_id:
            return jsonify({'code': -1, 'message': 'id不能为空'}), 400
        if tab_id is None:
            return jsonify({'code': -1, 'message': 'tab_id不能为空'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        update_sql = """
            UPDATE lovart_design_tab_mapping 
            SET tab_id = %s, tab_url = COALESCE(%s, tab_url), status = 'generating', updated_at = NOW()
            WHERE id = %s AND status IN ('ai_selected', 'tab_closed', 'generating', 'failed')
        """
        cursor.execute(update_sql, (tab_id, tab_url, mapping_id))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'code': -1,
                'message': '未找到对应的记录或状态不正确（待审核或已失败可更换 Tab）'
            }), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            'code': 0,
            'message': '已更换为该 Tab，状态已设为生成中',
            'data': {'id': mapping_id, 'tab_id': tab_id}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': f'操作失败: {str(e)}'}), 500


@app.route('/api/design/add-original-image', methods=['POST'])
def add_original_image():
    """人工添加商品原图 URL，追加到 original_images_urls，用于补充参考图。支持一次传多个 URL（image_urls 数组）。"""
    try:
        data = request.json
        mapping_id = data.get('id')
        image_urls = data.get('image_urls')
        image_url = data.get('image_url')
        if not mapping_id:
            return jsonify({'code': -1, 'message': 'id不能为空'}), 400
        if image_urls is not None:
            if not isinstance(image_urls, list):
                return jsonify({'code': -1, 'message': 'image_urls 必须是数组'}), 400
            to_add = [u.strip() for u in image_urls if u and isinstance(u, str) and u.strip()]
        elif image_url and isinstance(image_url, str):
            url_stripped = image_url.strip()
            to_add = [url_stripped] if url_stripped else []
        else:
            to_add = []
        if not to_add:
            return jsonify({'code': -1, 'message': '请至少提供一个有效的 image_url 或 image_urls'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, original_image_url, original_images_urls FROM lovart_design_tab_mapping WHERE id = %s',
            (mapping_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        urls = row['original_images_urls']
        if urls:
            try:
                urls = json.loads(urls) if isinstance(urls, str) else urls
            except Exception:
                urls = []
        if not isinstance(urls, list):
            urls = []
        urls.extend(to_add)
        first_url = row['original_image_url'] or (to_add[0] if to_add else None)
        cursor.execute(
            """UPDATE lovart_design_tab_mapping 
               SET original_image_url = COALESCE(original_image_url, %s), original_images_urls = %s, updated_at = NOW() 
               WHERE id = %s""",
            (first_url, json.dumps(urls, ensure_ascii=False), mapping_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            'code': 0,
            'message': f'已添加 {len(to_add)} 张原图',
            'data': {'id': mapping_id, 'count': len(urls)}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': f'操作失败: {str(e)}'}), 500


@app.route('/api/design/upload-design-image', methods=['POST'])
def upload_design_image():
    """本地上传设计图：multipart 文件，存到 DESIGN_IMAGES_DIR，返回可访问 URL（/images/xxx）。"""
    import time
    import uuid
    try:
        if 'file' not in request.files and 'image' not in request.files:
            return jsonify({'code': -1, 'message': '请选择要上传的图片文件'}), 400
        f = request.files.get('file') or request.files.get('image')
        if not f or not f.filename:
            return jsonify({'code': -1, 'message': '未选择有效文件'}), 400
        ext = os.path.splitext(f.filename)[1]
        if not ext or not DESIGN_UPLOAD_EXT.match(ext):
            return jsonify({'code': -1, 'message': '仅支持 png/jpg/jpeg/webp'}), 400
        mapping_id = request.form.get('id', '0')
        safe_id = re.sub(r'[^\w\-]', '', str(mapping_id))[:32] if mapping_id else '0'
        base_dir = os.path.abspath(DESIGN_IMAGES_DIR)
        os.makedirs(base_dir, exist_ok=True)
        ts = int(time.time() * 1000)
        uid = uuid.uuid4().hex[:8]
        filename = f'design_upload_{safe_id}_{ts}_{uid}{ext}'
        path = os.path.join(base_dir, filename)
        path = os.path.abspath(path)
        if not path.startswith(base_dir) or os.path.dirname(path) != base_dir:
            return jsonify({'code': -1, 'message': '文件名非法'}), 400
        f.save(path)
        url = f'/images/{filename}'
        return jsonify({'code': 0, 'message': 'success', 'data': {'url': url, 'filename': filename}})
    except Exception as e:
        return jsonify({'code': -1, 'message': f'上传失败: {str(e)}'}), 500


@app.route('/api/design/add-design-image', methods=['POST'])
def add_design_image():
    """将上传后的设计图 URL 追加到该记录的 design_images，并视情况追加到 design_images_uploaded_urls（本服务 /images/ 则同时写入，供 AI 推荐拉图）。"""
    try:
        data = request.json
        mapping_id = data.get('id')
        image_urls = data.get('image_urls')
        image_url = data.get('image_url')
        if not mapping_id:
            return jsonify({'code': -1, 'message': 'id不能为空'}), 400
        if image_urls is not None:
            if not isinstance(image_urls, list):
                return jsonify({'code': -1, 'message': 'image_urls 必须是数组'}), 400
            to_add = [u.strip() for u in image_urls if u and isinstance(u, str) and u.strip()]
        elif image_url and isinstance(image_url, str):
            to_add = [image_url.strip()] if image_url.strip() else []
        else:
            to_add = []
        if not to_add:
            return jsonify({'code': -1, 'message': '请至少提供一个有效的 image_url 或 image_urls'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, design_images, design_images_uploaded_urls FROM lovart_design_tab_mapping WHERE id = %s',
            (mapping_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'code': -1, 'message': '未找到对应记录'}), 404
        design_images = row.get('design_images')
        if design_images is not None and isinstance(design_images, str) and design_images.strip():
            try:
                design_images = json.loads(design_images)
            except Exception:
                design_images = []
        if not isinstance(design_images, list):
            design_images = []
        uploaded_raw = row.get('design_images_uploaded_urls')
        if uploaded_raw is not None and isinstance(uploaded_raw, str) and uploaded_raw.strip():
            try:
                uploaded_list = json.loads(uploaded_raw)
            except Exception:
                uploaded_list = []
        else:
            uploaded_list = []
        if not isinstance(uploaded_list, list):
            uploaded_list = []
        base_url = request.url_root.rstrip('/')
        def is_same_origin(url):
            if not url:
                return False
            u = str(url).strip()
            if u.startswith('/images/'):
                return True
            if base_url and u.startswith(base_url):
                return True
            return False
        for u in to_add:
            design_images.append({'url': u, 'title': '本地上传'})
            idx_1based = len(design_images)
            if is_same_origin(u):
                full_url = u if (str(u).startswith('http://') or str(u).startswith('https://')) else ((base_url + u) if u.startswith('/') and base_url else u)
                uploaded_list.append({'index': idx_1based, 'url': full_url})
        design_images_json = json.dumps(design_images, ensure_ascii=False)
        uploaded_json = json.dumps(uploaded_list, ensure_ascii=False) if uploaded_list else None
        try:
            if uploaded_json:
                cursor.execute(
                    """UPDATE lovart_design_tab_mapping 
                       SET design_images = %s, design_images_uploaded_urls = %s, updated_at = NOW() 
                       WHERE id = %s""",
                    (design_images_json, uploaded_json, mapping_id)
                )
            else:
                cursor.execute(
                    """UPDATE lovart_design_tab_mapping 
                       SET design_images = %s, updated_at = NOW() 
                       WHERE id = %s""",
                    (design_images_json, mapping_id)
                )
        except pymysql.err.OperationalError as e:
            if 'Unknown column' in str(e) and 'design_images_uploaded_urls' in str(e):
                cursor.execute(
                    """UPDATE lovart_design_tab_mapping SET design_images = %s, updated_at = NOW() WHERE id = %s""",
                    (design_images_json, mapping_id)
                )
            else:
                raise
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            'code': 0,
            'message': f'已添加 {len(to_add)} 张设计图',
            'data': {'id': mapping_id, 'count': len(design_images)}
        })
    except Exception as e:
        return jsonify({'code': -1, 'message': f'操作失败: {str(e)}'}), 500


@app.route('/api/design/generating-list', methods=['GET'])
def get_generating_list():
    """查询生成中的Tab列表（N8N检测工作流调用）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT id, tab_id, tab_url, product_id, product_name, category
            FROM lovart_design_tab_mapping 
            WHERE status = 'generating'
            ORDER BY created_at DESC
        """
        cursor.execute(sql)
        items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': items
        })
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/image/proxy', methods=['GET'])
def proxy_image():
    """图片代理接口，用于绕过防盗链限制（特别是移动端）"""
    try:
        image_url = request.args.get('url')
        if not image_url:
            return jsonify({
                'code': -1,
                'message': 'url参数不能为空'
            }), 400
        
        # 只允许代理特定域名的图片（安全考虑）
        allowed_domains = ['lovart.ai', 'a.lovart.ai', 'img.kwcdn.com']
        parsed_url = urllib.parse.urlparse(image_url)
        if not any(parsed_url.netloc.endswith(domain) for domain in allowed_domains):
            return jsonify({
                'code': -1,
                'message': '不允许代理该域名的图片'
            }), 403
        
        # 设置请求头，模拟浏览器请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.lovart.ai/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        
        # 请求图片
        response = requests.get(image_url, headers=headers, timeout=10, stream=True)
        response.raise_for_status()
        
        # 返回图片内容
        from flask import Response
        return Response(
            response.content,
            mimetype=response.headers.get('Content-Type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*'
            }
        )
    except requests.exceptions.RequestException as e:
        return jsonify({
            'code': -1,
            'message': f'图片加载失败: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'code': -1,
            'message': f'代理失败: {str(e)}'
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
