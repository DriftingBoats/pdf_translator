# PDF 分页批量翻译工具

这是一个按页数分批处理的PDF翻译工具，支持自动识别标题、处理句子完整性，并最终整合为一个完整的翻译文档。

## 主要功能

1. **按页数分批翻译**：不再依赖预定义章节，而是按指定页数（如每5页）自动分批处理
2. **句子完整性处理**：如果分批边界刚好截断句子，会自动扩展到句子结束
3. **自动标题识别**：识别文档中的标题并在翻译中保持格式
4. **自动编号整合**：所有批次按顺序编号，最终整合为一个完整文档
5. **增量术语表**：自动维护和更新翻译术语表

## 配置文件

创建 `config.json` 文件（参考 `config_example.json`）：

```json
{
  "api": {
    "API_URL": "https://api.openai.com/v1/chat/completions",
    "API_KEY": "your-api-key-here",
    "LLM_MODEL": "gpt-4",
    "temperature": 0.2
  },
  "paths": {
    "pdf": "your-document.pdf",
    "output_dir": "output/your-document",
    "big_md_name": "translated_document.md"
  },
  "pages_per_batch": 5,
  "glossary": {
    "example_term": "示例术语"
  }
}
```

### 配置说明

- `pages_per_batch`: 每批处理的页数，默认为5页
- `pdf`: PDF文件路径
- `output_dir`: 输出目录
- `big_md_name`: 最终整合文档的文件名
- `glossary`: 预定义术语表（可选）

## 使用方法

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置API密钥和文件路径

3. 运行翻译：
```bash
python translator.py config.json
```

或者交互式选择配置文件：
```bash
python translator.py
```

## 输出文件

- `chap_md/`: 包含各批次的翻译文件（batch_001.md, batch_002.md等）
- `translated_document.md`: 最终整合的完整翻译文档
- `glossary.tsv`: 术语表文件
- `translation_report.txt`: 翻译质量报告
- `style_cache.txt`: 文档风格缓存
- `retry_config.json`: 失败批次的重试配置（如有）

## 新特性详解

### 1. 自动分批处理

脚本会根据 `pages_per_batch` 设置自动将PDF分成多个批次：
- 批次1：第1-5页
- 批次2：第6-10页
- 批次3：第11-15页
- ...

### 2. 句子完整性处理

当批次边界恰好在句子中间时，脚本会：
- 检测句子是否完整（以句号、问号、感叹号结尾）
- 如果不完整，尝试扩展到下一页直到句子结束
- 确保翻译的连贯性

### 3. 标题自动识别

脚本会自动识别以下类型的标题：
- 全大写的短行
- 以"Chapter"、"Part"、"Section"开头的行
- 居中的短行（不包含常见句子结构）

识别的标题会在翻译中标记为Markdown标题格式。

### 4. 错误处理和重试

如果某些批次翻译失败，脚本会：
- 生成详细的错误报告
- 创建重试配置文件
- 允许单独重新处理失败的批次

## 注意事项

1. 确保PDF文件可以正确提取文本
2. API密钥需要有足够的配额
3. 建议先用小的 `pages_per_batch` 值测试
4. 大文档建议分多次处理以避免API限制

## 故障排除

- 如果翻译质量不佳，可以调整 `temperature` 参数
- 如果经常超时，可以减少 `pages_per_batch` 的值
- 检查 `translation_report.txt` 了解详细的处理状态