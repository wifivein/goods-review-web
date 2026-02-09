// N8N 节点名：去重并确保规格图在目标位置
// 整段复制进该 Code 节点，替换原代码

const norm = (u) => (u || '').split('?')[0];

function canonicalDim(dimStr) {
  if (!dimStr || typeof dimStr !== 'string') return '';
  const m = dimStr.trim().match(/\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?/);
  if (!m) return '';
  const parts = m[0].toLowerCase().replace('×', 'x').split('x');
  const a = parseFloat(parts[0]), b = parseFloat(parts[1]);
  if (Number.isNaN(a) || Number.isNaN(b)) return '';
  const aStr = a === Math.round(a) ? String(Math.round(a)) : String(a);
  const bStr = b === Math.round(b) ? String(Math.round(b)) : String(b);
  return aStr + 'x' + bStr;
}
function extractNxNSetFromSkuList(skuList) {
  const set = new Set();
  if (!Array.isArray(skuList)) return set;
  const re = /\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?/g;
  function addFromStr(val) {
    if (typeof val !== 'string') return;
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(val)) !== null) { const c = canonicalDim(m[0]); if (c) set.add(c); }
  }
  const skipKeys = { volumeLen: 1, volumeWidth: 1, volumeHeight: 1, weightValue: 1, productSkuId: 1, imageIndex: 1, supplierPrice: 1, suggestedPrice: 1, pic_url: 1 };
  skuList.forEach(sku => {
    if (!sku || typeof sku !== 'object') return;
    Object.keys(sku).forEach(k => { if (skipKeys[k] != null) return; if (sku[k] != null) addFromStr(String(sku[k])); });
  });
  return set;
}
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
function imageDimMatchesTemplate(imageDimStr, templateDim) {
  if (!imageDimStr || !templateDim) return false;
  const imageNums = new Set(imageDimStr.trim().split(/[xX×]/).map(p => parseFloat(p.trim())).filter(n => !Number.isNaN(n)));
  const templateParts = templateDim.trim().split(/[xX×]/).map(p => parseFloat(p.trim())).filter(n => !Number.isNaN(n));
  if (templateParts.length < 2) return false;
  return templateParts.every(n => imageNums.has(n));
}

let labels = [], carousel = [];
try {
  if ($('合并规格图细分结果').isExecuted && $('合并规格图细分结果').first().json) {
    const merged = $('合并规格图细分结果').first().json;
    labels = merged.labels || []; carousel = merged.carousel || [];
  }
} catch (e) {}
if (!labels.length) {
  const v = $('汇总Vision打标结果').first().json;
  labels = v.labels || []; carousel = v.carousel || [];
}

const duplicateRes = $input.first().json;
const duplicateInfo = duplicateRes.data || duplicateRes || {};
const duplicateGroups = duplicateInfo.duplicate_groups || [];

const goods = $('商品字段内容').first().json;
const config = goods._category_config || {};
const targetIndex = config.spec_image_index ?? 2;
const defaultSpecUrl = (config.spec_image_url || '').trim();

const skuList = goods.sku_list || [];
// 多规格/单规格由品类配置决定，不再用 sku_list 数量（sku_list 绑定模板后才有）
const hasMultiSpec = !!(config.is_multi_spec);
const templateSpecSetFromGoods = extractNxNSetFromSkuList(skuList);

const urlToSpecSubtype = {};
const urlToImageType = {};
const urlToSpecDimensions = {};
carousel.forEach((url, i) => {
  const u = norm(url);
  if (u) {
    urlToSpecSubtype[u] = (labels[i] && labels[i].spec_subtype) || null;
    urlToImageType[u] = (labels[i] && labels[i].image_type) || null;
    urlToSpecDimensions[u] = (labels[i] && labels[i].spec_dimensions) || null;
  }
});

const isProductDisplay = (url) => urlToImageType[norm(url)] === 'product_display';

let list = carousel.filter(Boolean);
let dedupMsg = '未检测到重复图片，无需去重';
let actualDeletedCount = 0;

if (duplicateGroups.length > 0) {
  const toDelete = new Set();
  // 兼容两种接口格式：① group=[url,url] 多份同图 ② group=[url] 仅代表 URL，在 list 中该 URL 出现多次则删后续
  duplicateGroups.forEach(group => {
    if (!group || !group.length) return;
    const keyUrl = norm(group[0]);
    const indices = list.map((u, i) => (norm(u) === keyUrl ? i : -1)).filter((i) => i >= 0);
    if (indices.length > 1) indices.slice(1).forEach((i) => toDelete.add(list[i]));
  });
  const remain = list.length - toDelete.size;
  if (remain >= 5) {
    list = list.filter((url) => !toDelete.has(url));
    actualDeletedCount = toDelete.size;
    dedupMsg = `检测到${duplicateGroups.length}组重复，删除${toDelete.size}张，剩余${list.length}张`;
  } else {
    dedupMsg = '检测到重复但删除后不足5张，保留原列表';
  }
}

const templateSpecSet = templateSpecSetFromGoods;
let specInsertMsg = '';

if (hasMultiSpec) {
  const multiSpecUrls = list.filter(u => urlToSpecSubtype[norm(u)] === 'multi_spec');
  if (multiSpecUrls.length >= 1) {
    list = list.filter(u => urlToSpecSubtype[norm(u)] !== 'multi_spec');
    list.splice(Math.min(targetIndex, list.length), 0, multiSpecUrls[0]);
    specInsertMsg = '目标位已放入多规格图';
  } else {
    if (defaultSpecUrl) {
      list.splice(Math.min(targetIndex, list.length), 0, defaultSpecUrl);
      specInsertMsg = '目标位已插入默认规格图（多规格品类）';
    }
  }
  list = list.filter(url => {
    if (urlToSpecSubtype[norm(url)] !== 'single_spec') return true;
    const dim = normalizeSpecDim(urlToSpecDimensions[norm(url)]);
    if (!dim || templateSpecSet.size === 0) return true;
    return [...templateSpecSet].some(t => imageDimMatchesTemplate(dim, t));
  });
} else {
  const matchingSingleSpecUrls = list.filter(u => {
    if (urlToSpecSubtype[norm(u)] !== 'single_spec') return false;
    const dim = normalizeSpecDim(urlToSpecDimensions[norm(u)]);
    return dim && templateSpecSet.size > 0 && [...templateSpecSet].some(t => imageDimMatchesTemplate(dim, t));
  });
  list = list.filter(u => urlToSpecSubtype[norm(u)] !== 'single_spec');
  if (matchingSingleSpecUrls.length >= 1) {
    list.splice(Math.min(targetIndex, list.length), 0, matchingSingleSpecUrls[0]);
    specInsertMsg = '目标位已放入符合模板的单规格图';
  } else if (defaultSpecUrl) {
    list.splice(Math.min(targetIndex, list.length), 0, defaultSpecUrl);
    specInsertMsg = '目标位已插入默认规格图（单规格品类）';
  } else {
    specInsertMsg = '无符合模板的单规格图且无默认图，未插入';
  }
}

if (list.length > 0 && !isProductDisplay(list[0])) {
  const firstProductIndex = list.findIndex(u => isProductDisplay(u));
  if (firstProductIndex > 0) {
    [list[0], list[firstProductIndex]] = [list[firstProductIndex], list[0]];
  }
}

let downloadCost = 0, processDuplicateCost = 0;
try {
  const t1 = $('计时1').first().json.currentDate;
  const t2 = $('计时2').first().json.currentDate;
  if (t1 && t2) downloadCost = Number(((new Date(t2) - new Date(t1)) / 1000).toFixed(2));
  if (typeof duplicateInfo.duplicate_detect_time === 'number') processDuplicateCost = duplicateInfo.duplicate_detect_time;
} catch (e) {}

const originalCount = carousel.filter(Boolean).length;
const toDeleteCount = actualDeletedCount;
const finalMessage = specInsertMsg ? `${dedupMsg}; ${specInsertMsg}` : dedupMsg;

return [{
  json: {
    image_list: list,
    image_list_reordered: list,
    download_cost: downloadCost,
    process_raw_cost: 0,
    process_duplicate_cost: processDuplicateCost,
    deduplication_info: {
      has_duplicates: duplicateInfo.has_duplicates || false,
      duplicate_groups: duplicateGroups,
      original_count: originalCount,
      to_delete_count: toDeleteCount,
      deduplicated_count: list.length,
      deduplicated: list.length !== originalCount,
      reason: dedupMsg
    },
    top_score_info: { target_index: targetIndex },
    audit_tips: '',
    message: finalMessage
  }
}];
