# 修复"Name not found"问题

## 问题分析

脚本返回 `"Name not found"`，说明虽然找到了元素，但文本内容不匹配。

可能的原因：
1. **文本内容不完全匹配**：实际DOM中的文本可能有额外的空格、换行符等
2. **Unicode编码问题**：`targetName` 是 `"31608983628方巾2"`，但DOM中可能存储方式不同
3. **选择器找到的元素不对**：可能找到了多个元素，但都不是目标元素

## 解决方案

改进脚本，使用更宽松的匹配方式，并添加调试信息：

### 方案1：使用 includes 匹配（推荐）

```javascript
try { 
  const name = args.targetName.trim(); 
  const allNames = Array.from(document.querySelectorAll("div[class*='text-ellipsis'][class*='font-semibold']")); 
  
  // 使用 includes 进行模糊匹配，而不是精确匹配
  const targetEl = allNames.find(el => {
    const text = el.textContent.trim();
    return text === name || text.includes(name) || name.includes(text);
  }); 
  
  if (!targetEl) {
    // 返回调试信息：找到了多少个元素，以及它们的文本内容
    const foundTexts = allNames.map(el => el.textContent.trim());
    return { 
      status: 'fail', 
      msg: `Name not found. Looking for: "${name}". Found ${allNames.length} elements: ${JSON.stringify(foundTexts)}` 
    }; 
  }
  
  const btn = targetEl.parentElement.nextElementSibling.querySelector('button'); 
  if (btn) { 
    btn.parentElement.style.visibility='visible'; 
    btn.click(); 
    return { status: 'success' }; 
  } 
  return { status: 'fail', msg: 'Btn not found' }; 
} catch(e) { 
  return { status: 'error', msg: e.toString() }; 
}
```

### 方案2：使用 normalize 处理文本（处理空格和换行）

```javascript
try { 
  const name = args.targetName.trim().replace(/\s+/g, ' '); // 规范化空格
  const allNames = Array.from(document.querySelectorAll("div[class*='text-ellipsis'][class*='font-semibold']")); 
  
  const targetEl = allNames.find(el => {
    const text = el.textContent.trim().replace(/\s+/g, ' '); // 规范化空格
    return text === name;
  }); 
  
  if (!targetEl) {
    const foundTexts = allNames.map(el => el.textContent.trim());
    return { 
      status: 'fail', 
      msg: `Name not found. Looking for: "${name}". Found: ${JSON.stringify(foundTexts)}` 
    }; 
  }
  
  const btn = targetEl.parentElement.nextElementSibling.querySelector('button'); 
  if (btn) { 
    btn.parentElement.style.visibility='visible'; 
    btn.click(); 
    return { status: 'success' }; 
  } 
  return { status: 'fail', msg: 'Btn not found' }; 
} catch(e) { 
  return { status: 'error', msg: e.toString() }; 
}
```

### 方案3：先调试，看实际找到了什么（推荐先用这个）

```javascript
try { 
  const name = args.targetName.trim(); 
  const allNames = Array.from(document.querySelectorAll("div[class*='text-ellipsis'][class*='font-semibold']")); 
  
  // 返回调试信息
  const foundTexts = allNames.map(el => ({
    text: el.textContent.trim(),
    html: el.innerHTML,
    classes: el.className
  }));
  
  const targetEl = allNames.find(el => el.textContent.trim() === name); 
  
  if (!targetEl) {
    return { 
      status: 'fail', 
      msg: `Name not found. Looking for: "${name}". Found ${allNames.length} elements.`,
      debug: {
        lookingFor: name,
        foundCount: allNames.length,
        foundTexts: foundTexts
      }
    }; 
  }
  
  const btn = targetEl.parentElement.nextElementSibling.querySelector('button'); 
  if (btn) { 
    btn.parentElement.style.visibility='visible'; 
    btn.click(); 
    return { status: 'success' }; 
  } 
  return { status: 'fail', msg: 'Btn not found' }; 
} catch(e) { 
  return { status: 'error', msg: e.toString() }; 
}
```

## 建议

1. **先用方案3**运行一次，看看实际找到了哪些元素和文本
2. 根据调试信息，确定是匹配问题还是选择器问题
3. 如果文本内容确实不匹配，使用方案1的模糊匹配
4. 如果文本有空格/换行问题，使用方案2的规范化处理

## 在n8n中的配置

将 `jsonBody` 中的 `script` 字段替换为上述方案中的任意一个（推荐先用方案3调试）。
