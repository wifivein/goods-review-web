-- 负向操作原因历史：供「废弃/删图/badcase」弹窗的标签可选来源，按维度区分
-- 执行前请确认数据库为 temu_baodan（与 goods_review_web 同库）

CREATE TABLE IF NOT EXISTS negative_reason_log (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  dimension VARCHAR(16) NOT NULL COMMENT 'goods=商品维度(废弃), carousel=轮播图维度(删图/badcase)',
  reason VARCHAR(512) NOT NULL DEFAULT '' COMMENT '原因文案',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_dimension_created (dimension, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='负向操作原因历史';
