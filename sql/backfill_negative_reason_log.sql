-- 把以前填过的原因初始化到 negative_reason_log（执行前需已建表 add_negative_reason_log.sql）
-- 需在同一 MySQL 实例下执行（能访问 temu_baodan 与 temu_baodan_lab）

USE temu_baodan;

-- 1. 轮播图维度：从 label_badcase.feedback_note 取历史原因（去重，保留最早一条时间）
INSERT IGNORE INTO negative_reason_log (dimension, reason, created_at)
SELECT 'carousel', TRIM(feedback_note), MIN(created_at)
FROM label_badcase
WHERE feedback_note IS NOT NULL AND TRIM(feedback_note) != ''
GROUP BY TRIM(feedback_note);

-- 2. 商品维度：从 preview-lab 的 audit_feedback（废弃时的 human_note）取历史原因
INSERT IGNORE INTO negative_reason_log (dimension, reason, created_at)
SELECT 'goods', TRIM(human_note), MIN(created_at)
FROM temu_baodan_lab.audit_feedback
WHERE action = 'discard' AND human_note IS NOT NULL AND TRIM(human_note) != ''
GROUP BY TRIM(human_note);
