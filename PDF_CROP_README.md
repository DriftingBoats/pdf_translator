# PDF裁切功能使用指南

## 功能概述

PDF裁切功能可以帮助您在翻译过程中自动去除PDF文档的页眉页脚，提高翻译质量和效率。该功能支持：

- 🔍 **自动检测页眉页脚**：智能识别重复出现的页眉页脚内容
- ✂️ **手动裁切边距**：指定上下左右边距进行精确裁切
- 📊 **布局分析**：分析页面文本块分布，识别潜在的页眉页脚区域
- 💾 **缓存优化**：裁切结果会被缓存，避免重复处理

## 配置方法

### 1. 在配置文件中启用PDF裁切

在您的 `config.json` 文件中添加 `pdf_crop` 配置项：

```json
{
  "api": {
    "API_URL": "https://api.openai.com/v1/chat/completions",
    "API_KEY": "your-api-key-here",
    "LLM_MODEL": "gpt-4",
    "temperature": 0.2
  },
  "paths": {
    "pdf": "input.pdf",
    "output_dir": "output",
    "big_md_name": "translated_book.md"
  },
  "pages_per_batch": 10,
  "pdf_crop": {
    "enable": true,
    "margins": {
      "top": 50,
      "bottom": 50,
      "left": 0,
      "right": 0
    },
    "auto_detect_headers": true
  }
}
```

### 2. 配置参数说明

- **`enable`**: 是否启用PDF裁切功能（true/false）
- **`margins`**: 裁切边距设置（单位：像素）
  - `top`: 上边距，去除页眉区域
  - `bottom`: 下边距，去除页脚区域
  - `left`: 左边距
  - `right`: 右边距
- **`auto_detect_headers`**: 是否启用自动检测页眉页脚（true/false）

## 使用方法

### 方法1：在翻译过程中自动应用

配置好后，直接运行翻译脚本：

```bash
python translator.py config_with_crop.json
```

翻译过程中会自动应用PDF裁切，日志中会显示裁切状态：

```
🔍 自动检测页眉页脚区域...
📊 检测到潜在页眉页脚区域: 15 个
✂️  PDF裁切已启用，边距设置: {'top': 50, 'bottom': 50, 'left': 0, 'right': 0}
```

### 方法2：单独测试PDF裁切功能

使用测试脚本预览裁切效果：

```bash
python test_pdf_crop.py your_document.pdf
```

这会显示：
- 页面布局分析结果
- 检测到的页眉页脚区域
- 裁切前后的文本对比

## 高级用法

### 自定义裁切策略

您可以根据不同类型的PDF文档调整裁切参数：

**学术论文**（通常有页眉页脚）：
```json
"pdf_crop": {
  "enable": true,
  "margins": {
    "top": 60,
    "bottom": 40,
    "left": 0,
    "right": 0
  },
  "auto_detect_headers": true
}
```

**小说书籍**（页眉可能包含章节信息）：
```json
"pdf_crop": {
  "enable": true,
  "margins": {
    "top": 30,
    "bottom": 30,
    "left": 0,
    "right": 0
  },
  "auto_detect_headers": false
}
```

**技术文档**（可能有复杂的页眉页脚）：
```json
"pdf_crop": {
  "enable": true,
  "margins": {
    "top": 80,
    "bottom": 60,
    "left": 20,
    "right": 20
  },
  "auto_detect_headers": true
}
```

### 程序化使用

您也可以在代码中直接使用PDF裁切工具：

```python
from pdf_crop_tool import PDFCropTool

# 初始化工具
crop_tool = PDFCropTool("document.pdf")

# 分析页面布局
analysis = crop_tool.analyze_layout()
print(f"检测到 {len(analysis)} 个潜在页眉页脚区域")

# 手动裁切指定页面
crop_tool.crop_page(0, top=50, bottom=50)

# 自动裁切（基于检测结果）
crop_tool.auto_crop_page(1, top=30, bottom=30)

# 预览裁切效果
preview = crop_tool.preview_crop_analysis()

# 关闭工具
crop_tool.close()
```

## 注意事项

1. **备份原文件**：虽然裁切不会修改原始PDF文件，但建议备份重要文档

2. **测试裁切效果**：首次使用时建议先用测试脚本预览效果，确保裁切参数合适

3. **性能考虑**：启用PDF裁切会增加一些处理时间，但结果会被缓存

4. **兼容性**：该功能基于PyMuPDF，支持大多数PDF格式

5. **文本质量**：正确的裁切可以显著提高翻译质量，避免页眉页脚干扰

## 故障排除

### 常见问题

**Q: 裁切后文本丢失过多？**
A: 减小边距值，或关闭自动检测，使用手动裁切

**Q: 页眉页脚仍然存在？**
A: 增大相应边距值，或启用自动检测功能

**Q: 处理速度变慢？**
A: 这是正常现象，裁切结果会被缓存，后续处理会更快

**Q: 某些页面裁切失败？**
A: 检查日志中的警告信息，可能是PDF格式问题，会自动回退到原始页面

### 调试模式

如需详细的调试信息，可以在配置中启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 示例文件

- `config_with_crop.json`: 包含PDF裁切配置的示例配置文件
- `test_pdf_crop.py`: PDF裁切功能测试脚本
- `pdf_crop_tool.py`: PDF裁切工具核心实现

通过合理配置PDF裁切功能，您可以显著提高PDF翻译的质量和效率！