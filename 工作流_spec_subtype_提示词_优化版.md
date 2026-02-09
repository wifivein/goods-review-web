# spec_subtype 提示词（多规格 vs 单规格）

用于 preview-lab 场景 `spec_subtype`。无兜底：拉不到或为空时接口直接 502。

---

**以下整段复制到 preview-lab → 场景 spec_subtype → Prompt 内容，保存并设为当前版本。**

---

**V2：乘号启发 + 同一规格的多种展示不算多规格**

```
这是一张规格图（以尺寸/规格参数为主）。请按下面顺序判断，只输出 JSON。

【重要】同一商品、同一规格的多种展示（如正视图+侧视图同屏、或长/宽/高 分条标注）仍算 single_spec，不要因为同屏有多块图或多组数字就判 multi_spec。

若图中有多组数字/尺寸，但**没有出现乘号（× 或 x）**（如只有 23cm、17cm、6cm 这类分条标注，或正视图标长、侧视图标高和厚），多为同一规格的长宽高/多视角展示，优先判 single_spec。真正的多规格图通常会有多组「宽×高」形式的尺寸（带 ×），对应多种可选规格供用户选择。

【必须判 multi_spec】尺码表/Size chart/多档尺寸选择图：图中标题或内容明确为「尺码表」「Size chart」「Blanket Sizes」「please choose your size」等，且用多块区域、多组尺寸（如多组 宽×高 或 多档 inch/cm 并列/嵌套）展示**多种可选规格**（如小/中/大、多档尺寸供用户选）时，一律判 multi_spec，不要判 single_spec。

- single_spec：① 同一商品的正视图+侧视图（或长/宽/高 分条标注）；② 只有一对宽×高；③ 有多组数字但没有 ×；④ 不是尺码表/多档尺寸选择图。以上判 single_spec。

- multi_spec：① 图中出现**多组带乘号（×）的尺寸**（如 76×101、50×60、60×80 等），且分别对应不同可选规格/SKU；② 或图为尺码表/Size chart/多档尺寸选择（见上）。判 multi_spec。

只输出以下 JSON，不要换行、不要其他文字、不要 markdown 代码块：
{"spec_subtype":"multi_spec或single_spec"}
```
