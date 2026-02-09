// ===================== 0. 单规格图按模板过滤（工具函数） =====================
// 将 "15.0x22.0" / "15x22" 统一为可比较的规范串（数值等价：整数去掉 .0），避免模板无小数点、打标有小数点导致误删
function canonicalDim(dimStr) {
  if (!dimStr || typeof dimStr !== 'string') return '';
  const m = dimStr.trim().match(/\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?/);
  if (!m) return '';
  const parts = m[0].toLowerCase().replace('×', 'x').split('x');
  const a = parseFloat(parts[0]);
  const b = parseFloat(parts[1]);
  if (Number.isNaN(a) || Number.isNaN(b)) return '';
  const aStr = a === Math.round(a) ? String(Math.round(a)) : String(a);
  const bStr = b === Math.round(b) ? String(Math.round(b)) : String(b);
  return aStr + 'x' + bStr;
}
// 从模板中收集所有规格文案里的 NxN（存入规范形式，便于与打标结果比较）
function extractNxNSet(templateData) {
  const set = new Set();
  if (!templateData || typeof templateData !== 'object') return set;
  const re = /\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?/g;
  function addFromStr(val) {
    if (typeof val !== 'string') return;
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(val)) !== null) {
      const c = canonicalDim(m[0]);
      if (c) set.add(c);
    }
  }
  const skipKeys = { volumeLen: 1, volumeWidth: 1, volumeHeight: 1, weightValue: 1, productSkuId: 1, imageIndex: 1, supplierPrice: 1, suggestedPrice: 1 };
  (templateData.productSkuSpecTableData || []).forEach(item => {
    if (!item) return;
    Object.keys(item).forEach(k => {
      if (skipKeys[k] != null) return;
      if (item[k] != null) addFromStr(String(item[k]));
    });
  });
  (templateData.productSkuSpecList || []).forEach(item => {
    if (!item || !item.productSkuSpecs) return;
    Object.values(item.productSkuSpecs || {}).forEach(val => { if (val != null) addFromStr(String(val)); });
  });
  return set;
}
// spec_dimensions 可能是对象 { cm: "5x18x22", inches: "" } 或 "18x22"，优先用 cm。支持 2 个或 3 个（长宽高）数字，统一为升序 x 连接。
function normalizeSpecDim(specDimensions) {
  if (specDimensions == null) return '';
  let str = '';
  if (typeof specDimensions === 'object') str = specDimensions.cm || specDimensions.inches || '';
  else str = String(specDimensions);
  const parts = (str.match(/\d+(?:\.\d+)?/g) || []).map(s => parseFloat(s)).filter(n => !Number.isNaN(n));
  if (parts.length === 0) return '';
  parts.sort((a, b) => a - b);
  const fmt = (n) => n === Math.round(n) ? String(Math.round(n)) : String(Number(n.toFixed(2)));
  return parts.map(fmt).join('x');
}
// 图片维度（可能 2 或 3 个数，如 18x22 或 5x18x22）是否与模板维度（两数，如 18x22）匹配：模板的两个数都在图片数值集合内即算匹配
function imageDimMatchesTemplate(imageDimStr, templateDim) {
  if (!imageDimStr || !templateDim) return false;
  const imageNums = new Set(imageDimStr.trim().split(/[xX×]/).map(p => parseFloat(p.trim())).filter(n => !Number.isNaN(n)));
  const templateParts = templateDim.trim().split(/[xX×]/).map(p => parseFloat(p.trim())).filter(n => !Number.isNaN(n));
  if (templateParts.length < 2) return false;
  return templateParts.every(n => imageNums.has(n));
}

// ===================== 1. 读取数据 =====================
const productData = $('去重并确保规格图在目标位置').first().json;
if (!productData) throw new Error('无法获取产品数据');

const templates = $input.all().map(item => item.json || {});
const targetTemplateName = $('商品字段内容').first().json._category_config.template_name;
const templateV2 = templates.find(tpl => tpl.name === targetTemplateName || tpl.title === targetTemplateName);
if (!templateV2) throw new Error(`未找到名称为"${targetTemplateName}"的模板`);

let templateFullData = templateV2.data;
if (typeof templateFullData === 'string') templateFullData = JSON.parse(templateFullData);

const skuTableData = templateFullData.productSkuSpecTableData || [];
if (skuTableData.length === 0) throw new Error("模板中未找到 SKU 规格表数据");

// ===================== 2. 按模板过滤单规格图 =====================
let reorderedImages = productData.image_list_reordered || productData.image_list || [];
const templateSpecSet = extractNxNSet(templateFullData);

let labels = [], carousel = [];
try {
  if ($('合并规格图细分结果').isExecuted && $('合并规格图细分结果').first().json) {
    const merged = $('合并规格图细分结果').first().json;
    labels = merged.labels || [];
    carousel = merged.carousel || [];
  } else {
    const v = $('汇总Vision打标结果').first().json;
    labels = v.labels || [];
    carousel = v.carousel || [];
  }
} catch (e) {}

const norm = (u) => (u || '').split('?')[0];
const urlToLabel = {};
labels.forEach((l, i) => {
  const url = (l.original_url || l.image_url || carousel[i] || '');
  if (norm(url)) urlToLabel[norm(url)] = l;
});

const specFilterLog = { template_dims: [...templateSpecSet], removed: [], kept_single_spec: [], reason: '' };
reorderedImages = reorderedImages.filter((url) => {
  const lab = urlToLabel[norm(url)];
  if (!lab || lab.spec_subtype !== 'single_spec') return true;
  const dim = normalizeSpecDim(lab.spec_dimensions);
  if (!dim) return true;
  if (templateSpecSet.size === 0) return true;
  const keep = [...templateSpecSet].some(t => imageDimMatchesTemplate(dim, t));
  if (keep) specFilterLog.kept_single_spec.push({ url: norm(url), dim });
  else specFilterLog.removed.push({ url: norm(url), dim, raw: lab.spec_dimensions });
  return keep;
});

// 按 URL 去重：同一张图在列表中多次出现只保留第一次，避免“保留 N 张”把重复算进去且输出列表含重复
const seen = new Set();
reorderedImages = reorderedImages.filter((url) => {
  const key = norm(url);
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
});

// 统计按唯一 URL 算的单规格图数量，用于文案
const keptUniqueByUrl = [...new Map(specFilterLog.kept_single_spec.map((r) => [r.url, r])).values()];
const keptUniqueCount = keptUniqueByUrl.length;
if (specFilterLog.removed.length > 0) {
  specFilterLog.reason = `单规格图按模板过滤：保留与模板尺寸一致的 ${keptUniqueCount} 张（唯一 URL），移除 ${specFilterLog.removed.length} 张（尺寸不在模板中）。模板尺寸：${specFilterLog.template_dims.join(', ')}；移除项尺寸：${specFilterLog.removed.map(r => r.dim).join(', ')}`;
} else if (keptUniqueCount > 0) {
  const dupNote = specFilterLog.kept_single_spec.length > keptUniqueCount ? `；列表中重复出现 ${specFilterLog.kept_single_spec.length - keptUniqueCount} 次已去重` : '';
  specFilterLog.reason = `单规格图按模板过滤：保留 ${keptUniqueCount} 张单规格图（尺寸与模板一致：${[...new Set(keptUniqueByUrl.map(r => r.dim))].join(', ')}），未移除任何图${dupNote}`;
} else {
  specFilterLog.reason = '单规格图按模板过滤：未发现 single_spec 或模板无尺寸，未做移除';
}
specFilterLog.kept_single_spec = keptUniqueByUrl;

// ===================== 3. 获取补全图片 =====================
const firstImage = reorderedImages[0] || "";
if (!firstImage) throw new Error("商品图片列表为空，无法补全规格图");

// ===================== 4. 核心转换逻辑 =====================
const processedSkuList = skuTableData.map(sku => {
  const newSku = {
    productSkuId: sku.productSkuId || "",
    pic_url: firstImage,
    volumeLen: parseFloat(sku.volumeLen || 0),
    volumeWidth: parseFloat(sku.volumeWidth || 0),
    volumeHeight: parseFloat(sku.volumeHeight || 0),
    weightValue: parseFloat(sku.weightValue || 0),
    supplierPrice: String(sku.supplierPrice || 0),
    suggestedPrice: String(sku.suggestedPrice || 0),
    imageIndex: null
  };
  Object.keys(sku).forEach(key => {
    if (!isNaN(key)) newSku[key] = sku[key];
  });
  return newSku;
});

// ===================== 5. 组装输出 =====================
const finalProductData = {
  ...productData,
  image_list: reorderedImages,
  sku_list: processedSkuList,
  spec_filter: specFilterLog,
  message: productData.message ? `${productData.message}; ${specFilterLog.reason}` : specFilterLog.reason
};

return [{ json: finalProductData }];
