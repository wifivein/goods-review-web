# 数据库设计方案分析：扩展表 vs 新建表

## 📊 当前情况

- **存量数据**: 979条记录，只用于排重
- **新API结构**: 字段有变化，不完全对应
- **未来需求**: 围绕新版本进行开发

## 🔄 方案对比

### 方案1：扩展现有表 `temu_goods`

#### ✅ 优点
1. **数据连续性**: 所有数据在一个表中，查询简单
2. **代码改动小**: 现有代码可以继续使用
3. **迁移成本低**: 不需要数据迁移

#### ❌ 缺点
1. **表结构复杂**: 新旧字段混在一起，字段越来越多
2. **维护困难**: 需要区分哪些字段是新版，哪些是旧版
3. **性能影响**: 表结构臃肿，索引可能不够优化
4. **扩展性差**: 未来再有版本变化，表会越来越复杂
5. **代码混乱**: 需要大量 `if-else` 判断新旧版本

### 方案2：新建表 `temu_goods_v2`（推荐）

#### ✅ 优点
1. **结构清晰**: 新表完全按照新API结构设计，字段一一对应
2. **易于维护**: 新旧数据分离，逻辑清晰
3. **性能优化**: 新表结构精简，只包含必要字段
4. **扩展性好**: 未来版本变化可以再建新表
5. **代码简洁**: 新代码只处理新表，逻辑简单
6. **排重方便**: 可以同时查询两个表的 `product_id` 进行排重

#### ❌ 缺点
1. **需要新建表**: 需要设计新表结构
2. **代码需要适配**: 需要修改部分查询逻辑
3. **需要维护两个表**: 但旧表只读，影响不大

## 🎯 推荐方案：新建表 `temu_goods_v2`

### 理由

1. **老数据只用于排重**
   - 不需要频繁查询老数据
   - 排重时只需要查询 `product_id`，可以同时查两个表
   - 老表保持只读，不会影响性能

2. **新API结构更清晰**
   - 新表可以完全按照新API结构设计
   - 字段一一对应，不需要复杂的转换逻辑
   - 代码更简洁，维护更容易

3. **未来扩展性**
   - 如果再有版本变化，可以再建新表
   - 不会导致表结构越来越复杂
   - 保持代码和数据的清晰性

4. **性能考虑**
   - 新表结构精简，只包含必要字段
   - 索引可以针对新API的查询模式优化
   - 老表数据量不大（979条），排重查询性能影响小

## 📋 实施建议

### 新表结构设计

```sql
CREATE TABLE `temu_goods_v2` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `product_id` varchar(50) NOT NULL COMMENT '商品ID（字符串）',
  `product_name` varchar(500) NOT NULL COMMENT '商品名称',
  `origin_product_url` text NOT NULL COMMENT '原始商品URL',
  `carousel_pic_urls` json NOT NULL COMMENT '轮播图URL列表',
  `main_image` varchar(500) NOT NULL COMMENT '主图（轮播图第一张）',
  `cover` varchar(500) NOT NULL COMMENT '封面图（同主图）',
  `sku_list` json DEFAULT NULL COMMENT 'SKU列表',
  `sku_specs` json DEFAULT NULL COMMENT 'SKU规格',
  `sale_count` int DEFAULT 0 COMMENT '销量',
  `infringement_num` int DEFAULT NULL COMMENT '侵权编号',
  `infringement_status` tinyint DEFAULT 0 COMMENT '侵权状态',
  `extcode` varchar(50) DEFAULT NULL COMMENT '扩展代码',
  `is_publish` tinyint DEFAULT 0 COMMENT '是否发布',
  `master_user_id` bigint DEFAULT NULL COMMENT '主用户ID',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `group_id` bigint DEFAULT NULL COMMENT '分组ID',
  `ref_product_template_id` bigint DEFAULT NULL COMMENT '引用商品模板ID',
  `ref_product_size_template_id` bigint DEFAULT NULL COMMENT '引用尺寸模板ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_product_id` (`product_id`),
  KEY `idx_master_user_id` (`master_user_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_is_publish` (`is_publish`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表（新版本）';
```

### 排重查询逻辑

```python
def check_duplicate(product_id):
    """检查商品是否已存在（查询新旧两个表）"""
    # 查询新表
    sql_v2 = "SELECT id FROM temu_goods_v2 WHERE product_id = %s"
    # 查询老表（用于排重）
    sql_v1 = "SELECT id FROM temu_goods WHERE product_id = %s"
    
    # 如果任一表中有记录，则认为是重复
    return exists_in_v2 or exists_in_v1
```

### 代码迁移策略

1. **新功能**: 全部使用新表 `temu_goods_v2`
2. **排重功能**: 同时查询两个表
3. **老数据查询**: 保留老表的查询接口（如果需要）
4. **逐步迁移**: 如果将来需要，可以写脚本将老数据迁移到新表

## 📊 总结

**推荐：新建表 `temu_goods_v2`**

- ✅ 结构清晰，易于维护
- ✅ 性能更好，扩展性强
- ✅ 代码简洁，逻辑清晰
- ✅ 排重方便，不影响功能
- ✅ 未来扩展性好

**实施成本：**
- 需要设计新表结构（已提供）
- 需要修改部分代码使用新表
- 排重逻辑需要同时查询两个表（简单）

**长期收益：**
- 代码更清晰，维护更容易
- 性能更好，扩展性更强
- 不会因为版本变化导致表结构越来越复杂
