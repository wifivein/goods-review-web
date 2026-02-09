-- 品类配置增加「规格数量」：0=单规格 1=多规格，工作流按此判断不再依赖 sku_list 数量
ALTER TABLE goods_review_category_config
  ADD COLUMN is_multi_spec TINYINT(1) NOT NULL DEFAULT 0
  COMMENT '0=单规格 1=多规格'
  AFTER ref_product_template_id;
