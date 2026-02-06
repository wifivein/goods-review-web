-- 审核通过时被替换掉的规格图位置原 URL（按品类可能不是第3张）
ALTER TABLE temu_goods_v2
ADD COLUMN replaced_spec_image_url VARCHAR(1024) NULL DEFAULT NULL
COMMENT '审核通过时被替换掉的规格图位置原图URL，供以图搜图/query等使用';

-- 从旧字段迁移数据（执行完可择机废弃 replaced_3rd_image_url）
UPDATE temu_goods_v2
SET replaced_spec_image_url = replaced_3rd_image_url
WHERE replaced_3rd_image_url IS NOT NULL AND (replaced_spec_image_url IS NULL OR replaced_spec_image_url = '');
