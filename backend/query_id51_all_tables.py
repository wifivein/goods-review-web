#!/usr/bin/env python3
"""查 id=51 相关所有表：lovart_design_tab_mapping + image_assets（按 original_images_urls 的 url_hash）。"""
import os
import sys
import json
import hashlib

import pymysql

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '101.33.241.82'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'root'),
    'database': os.getenv('DB_NAME', 'temu_baodan'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}


def normalize_url(url):
    if not url or not isinstance(url, str):
        return ""
    return url.strip().split("#")[0].split("?")[0].strip()


def url_to_hash(url):
    n = normalize_url(url)
    return hashlib.md5(n.encode("utf-8")).hexdigest() if n else ""


def main():
    mapping_id = int((sys.argv[1:] or ['51'])[0])

    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 1. lovart_design_tab_mapping 整行（关键列）
    cur.execute(
        """SELECT id, tab_id, product_id, status,
                  original_image_url, original_images_urls,
                  original_excluded_indices, original_classify_reasons,
                  excluded_image_indices, design_images,
                  created_at, updated_at
           FROM lovart_design_tab_mapping WHERE id = %s""",
        (mapping_id,),
    )
    row = cur.fetchone()
    if not row:
        print(json.dumps({"error": "lovart_design_tab_mapping 无此 id", "id": mapping_id}, ensure_ascii=False, indent=2))
        cur.close()
        conn.close()
        return

    # 转成可 JSON 序列化（Decimal/datetime）
    def ser(o):
        if hasattr(o, 'isoformat'):
            return o.isoformat()
        if hasattr(o, '__float__') and not isinstance(o, bool):
            return float(o) if o is not None else None
        return o

    mapping = {k: ser(v) for k, v in row.items()}

    # 解析 original_images_urls
    urls_raw = mapping.get('original_images_urls')
    if isinstance(urls_raw, str) and urls_raw:
        try:
            urls = json.loads(urls_raw)
        except Exception:
            urls = []
    else:
        urls = urls_raw if isinstance(urls_raw, list) else []
    if not isinstance(urls, list):
        urls = []

    mapping['original_images_urls_parsed'] = urls
    mapping['original_images_urls_count'] = len(urls)

    # 2. 对每条 URL 算 url_hash，查 image_assets
    url_hashes = [url_to_hash(u) for u in urls]
    image_assets_rows = []
    if url_hashes:
        placeholders = ",".join(["%s"] * len(url_hashes))
        cur.execute(
            f"""SELECT id, url, url_hash, labels, label_source, source, created_at, updated_at
                 FROM image_assets WHERE url_hash IN ({placeholders})""",
            url_hashes,
        )
        image_assets_rows = cur.fetchall()

    # 转成可 JSON
    for r in image_assets_rows:
        for k, v in list(r.items()):
            r[k] = ser(v)
        if isinstance(r.get('labels'), str) and r.get('labels'):
            try:
                r['labels_parsed'] = json.loads(r['labels'])
            except Exception:
                r['labels_parsed'] = None

    # 按 original_images_urls 顺序对应到 image_assets（用 url_hash）
    hash_to_asset = {r['url_hash']: r for r in image_assets_rows}
    by_index = []
    for i, (u, h) in enumerate(zip(urls, url_hashes)):
        by_index.append({
            "index": i,
            "url": u[:100] + "..." if len(u) > 100 else u,
            "url_hash": h,
            "in_image_assets": h in hash_to_asset,
            "image_assets_row": hash_to_asset.get(h),
        })

    cur.close()
    conn.close()

    out = {
        "mapping_id": mapping_id,
        "lovart_design_tab_mapping": mapping,
        "image_assets_by_index": by_index,
        "image_assets_all_rows": image_assets_rows,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
