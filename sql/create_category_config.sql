-- 品类配置表：工作流与审核共用，审核页维护
-- 关键词匹配 product_category 字符串，命中任一即视为该品类
CREATE TABLE IF NOT EXISTS goods_review_category_config (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  config_key VARCHAR(32) NOT NULL COMMENT '品类键，如 blanket',
  display_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '展示名，如 毛毯',
  keywords JSON NOT NULL COMMENT '关键词数组，如 ["毯子","盖毯","毛毯"]',
  spec_image_index TINYINT UNSIGNED NOT NULL DEFAULT 2 COMMENT '规格图在轮播中的索引，0-based',
  spec_image_url VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '审核通过时替换为的标准规格图 URL',
  template_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '模板名，如 毛毯采集模板',
  ref_product_template_id INT UNSIGNED NULL DEFAULT NULL COMMENT '供应商侧模板 ID',
  sort_order INT NOT NULL DEFAULT 0 COMMENT '排序，越小越前',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_config_key (config_key),
  KEY idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='品类配置：关键词→规格图位置/URL/模板，工作流与审核共用';

-- 默认毛毯
INSERT INTO goods_review_category_config
  (config_key, display_name, keywords, spec_image_index, spec_image_url, template_name, ref_product_template_id, sort_order)
VALUES
  ('blanket', '毛毯', '["毯子","盖毯","毛毯"]', 2, 'https://img.kwcdn.com/product/20195053a14/c2ddafb8-2eee-497c-9c81-c45254e903bf_800x800.png', '毛毯采集模板', 50, 0)
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
