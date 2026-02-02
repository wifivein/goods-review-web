-- 轮播图大模型打标结果（待审核商品每张图一条）
USE temu_baodan;

ALTER TABLE temu_goods_v2
ADD COLUMN carousel_labels JSON NULL DEFAULT NULL
COMMENT '轮播图打标结果，与 carousel_pic_urls 同序：[{image_type,product_complete,shape,design_desc,quality_ok,first_image_score,first_image_reason,image_url},...]'
AFTER preprocess_tags;
