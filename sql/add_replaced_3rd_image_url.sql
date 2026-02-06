-- 审核通过时第3张会被替换为标准规格图，原第3张 URL 存于此字段，供后续 /api/image/query 等检索用
ALTER TABLE temu_goods_v2
ADD COLUMN replaced_3rd_image_url VARCHAR(1024) NULL DEFAULT NULL
COMMENT '审核通过时被替换掉的原第3张图URL，供以图搜图/query等使用';
