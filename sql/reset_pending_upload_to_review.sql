-- 把当前「待上传」的这批重置为「待审核」，便于重新走一遍审核
-- 条件与统计接口一致：process_status=2, review_status=1, is_publish=0, 且非侵权(2,3)
-- 执行后：待上传 -N，待审核 +N

UPDATE temu_goods_v2
SET review_status = 0
WHERE process_status = 2
  AND review_status = 1
  AND is_publish = 0
  AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3));

-- 查看影响行数（MySQL 会返回 Rows matched / Changed）
-- 若需先预览条数再决定是否执行，可先跑：
-- SELECT COUNT(*) FROM temu_goods_v2
-- WHERE process_status = 2 AND review_status = 1 AND is_publish = 0
--   AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3));
