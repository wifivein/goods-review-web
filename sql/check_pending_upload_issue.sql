-- 排查「待上传」194 可能卡在哪：api_id、侵权状态分布
-- 待上传定义（goods_review_web）：process_status=2, review_status=1, is_publish=0, 且 infringement_status 非 2/3
-- N8N 上传流只查 infringement_status=1，所以 infringement_status 为 NULL/0 的不会被 N8N 拉去发布！

SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN api_id IS NULL OR api_id = '' THEN 1 ELSE 0 END) AS api_id_empty,
  SUM(CASE WHEN api_id IS NOT NULL AND api_id != '' THEN 1 ELSE 0 END) AS api_id_ok,
  SUM(CASE WHEN infringement_status IS NULL THEN 1 ELSE 0 END) AS infringement_null,
  SUM(CASE WHEN infringement_status = 0 THEN 1 ELSE 0 END) AS infringement_0,
  SUM(CASE WHEN infringement_status = 1 THEN 1 ELSE 0 END) AS infringement_1
FROM temu_goods_v2
WHERE process_status = 2
  AND review_status = 1
  AND is_publish = 0
  AND (infringement_status IS NULL OR infringement_status NOT IN (2, 3));

-- infringement_1 才会被 N8N「查询已审核通过+侵权检测通过」节点选中；若多数是 null/0，就是卡在这。
