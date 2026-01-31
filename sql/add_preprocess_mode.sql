-- 添加预处理通道字段（快速通道 / 常规检查）
USE temu_baodan;

ALTER TABLE temu_goods_v2
ADD COLUMN preprocess_mode VARCHAR(20) NULL DEFAULT NULL
COMMENT '预处理通道：fast_path=快速通道，normal=常规检查，NULL=旧数据未记录'
AFTER process_status;
