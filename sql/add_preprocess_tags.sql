-- 通用预处理标签（可替代 preprocess_mode）
-- 支持多标签：["快速通道", "尺寸关键词命中", ...]，命中的规则依次追加
USE temu_baodan;

-- 1. 添加 preprocess_tags（JSON 数组）
ALTER TABLE temu_goods_v2
ADD COLUMN preprocess_tags JSON NULL DEFAULT NULL
COMMENT '预处理规则标签数组，如 ["快速通道","尺寸关键词命中"]'
AFTER process_status;

-- 2. 【若已执行过 add_preprocess_mode】迁移并删除旧字段
-- UPDATE temu_goods_v2 SET preprocess_tags = CASE
--   WHEN preprocess_mode = 'fast_path' THEN '["快速通道"]'
--   WHEN preprocess_mode = 'normal' THEN '["常规检查"]'
--   ELSE NULL END WHERE preprocess_mode IS NOT NULL;
-- ALTER TABLE temu_goods_v2 DROP COLUMN preprocess_mode;
