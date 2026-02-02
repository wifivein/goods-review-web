#!/usr/bin/env python3
"""用项目 DB 配置查 lovart_design_tab_mapping 的 original_excluded_indices / original_classify_reasons。"""
import os
import sys
import json

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

def main():
    id_arg = (sys.argv[1:] or ['51'])[0]
    try:
        limit_id = int(id_arg)
        where = "WHERE id = %s"
        params = (limit_id,)
    except ValueError:
        where = "ORDER BY id DESC LIMIT 5"
        params = ()

    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute(
            f"""SELECT id, original_images_urls, original_excluded_indices, original_classify_reasons
                FROM lovart_design_tab_mapping {where}""",
            params,
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        r['original_images_urls'] = (r.get('original_images_urls') or '')[:80] + '...' if (r.get('original_images_urls') and len(str(r.get('original_images_urls'))) > 80) else r.get('original_images_urls')
    print(json.dumps(rows, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
