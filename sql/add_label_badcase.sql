-- 标签 badcase 记录表：用于记录打标错误的样本，供后续分析和优化
-- 执行前请确认数据库

CREATE TABLE IF NOT EXISTS label_badcase (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  product_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '商品ID',
  image_url VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '图片URL',
  image_index INT NOT NULL DEFAULT 0 COMMENT '轮播图索引（0-based）',
  carousel_label JSON COMMENT '当前标签（完整对象）',
  feedback_type VARCHAR(32) NOT NULL DEFAULT '其他' COMMENT '问题类型：类型错误/描述不准确/打标失败误判/其他',
  feedback_note TEXT COMMENT '备注说明',
  suggested_correct TEXT COMMENT '建议的正确标签（JSON或自由文本）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_product_id (product_id),
  INDEX idx_created_at (created_at),
  INDEX idx_feedback_type (feedback_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标签badcase记录表';
