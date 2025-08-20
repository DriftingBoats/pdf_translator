# PDF 分页批量翻译工具

这是一个功能完整的PDF翻译工具套件，支持按页数分批处理、智能质量检测和自动优化，确保高质量的翻译输出。

## 🚀 核心功能

### 主翻译器 (translator.py)
1. **按页数分批翻译**：按指定页数（如每5页）自动分批处理，无需预定义章节
2. **句子完整性处理**：智能检测分批边界，自动扩展到句子结束确保连贯性
3. **自动标题识别**：识别文档中的标题并在翻译中保持Markdown格式
4. **自动编号整合**：所有批次按顺序编号，最终整合为完整文档
5. **增量术语表**：自动维护和更新翻译术语表，确保术语一致性
6. **实时质量监控**：自动检测段落数量差异，标记需要优化的批次
7. **LLM成本跟踪**：实时显示Token使用量和翻译成本

### 质量优化工具
1. **retranslate_batch.py**：快速重新翻译指定批次
2. **retranslate_diff_batches.py**：完整分析和批量优化工具
3. **list_books.py**：多书籍管理和质量分析工具

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

## 📋 完整使用流程

### 第一步：环境准备

1. **安装依赖**：
```bash
pip install -r requirements.txt
```

2. **配置文件设置**：
   - 复制 `config_example.json` 为 `config.json`
   - 配置API密钥、PDF路径和输出目录

### 第二步：主翻译流程

**运行主翻译器**：
```bash
# 使用指定配置文件
python translator.py config.json

# 交互式选择配置文件
python translator.py
```

**翻译过程监控**：
- 实时显示翻译进度和段落数量对比
- 自动标记质量问题批次（段落差异>20%）
- 显示LLM成本和Token使用统计

### 第三步：质量优化（**强烈推荐**）

**translator运行完成后，建议立即运行质量检查和优化：**

#### 方案A：快速优化（推荐）
```bash
# 交互式模式，用户友好
python retranslate_batch.py

# 自动处理所有问题批次
python retranslate_batch.py --all-diff

# 处理指定批次
python retranslate_batch.py 9 12 15
```

#### 方案B：完整分析
```bash
# 详细分析和交互式处理
python retranslate_diff_batches.py

# 自动分析和处理
python retranslate_diff_batches.py --auto
```

#### 方案C：多书籍管理
```bash
# 查看所有书籍状态
python list_books.py --detailed

# 处理指定书籍
python retranslate_batch.py --all-diff --book-dir "output/book1"
```

## 输出文件

- `chap_md/`: 包含各批次的翻译文件（batch_001.md, batch_002.md等）
- `translated_document.md`: 最终整合的完整翻译文档
- `glossary.tsv`: 术语表文件
- `translation_report.txt`: 翻译质量报告
- `style_cache.txt`: 文档风格缓存
- `retry_config.json`: 失败批次的重试配置（如有）

## 🔧 高级配置

### 配置文件增强功能

```json
{
  "api": {
    "API_URL": "https://api.openai.com/v1/chat/completions",
    "API_KEY": "your-api-key-here",
    "LLM_MODEL": "gpt-4o",
    "temperature": 0.2
  },
  "paths": {
    "pdf": "your-document.pdf",
    "output_dir": "output/your-document",
    "big_md_name": "translated_document.md"
  },
  "pages_per_batch": 5,
  "enable_cost_tracking": true,
  "pricing": {
    "gpt-4o": {
      "input_price_per_1k_tokens": 0.005,
      "output_price_per_1k_tokens": 0.015,
      "currency": "USD"
    }
  },
  "glossary": {
    "example_term": "示例术语"
  }
}
```

### 智能功能详解

#### 1. 自动分批处理
- 根据 `pages_per_batch` 设置自动分批
- 智能边界检测，避免句子截断
- 自动编号和整合

#### 2. 质量监控系统
- 实时段落数量对比：`📊 批次X段落数量对比: 输入Y段 → 输出Z段`
- 自动标记问题批次：差异>20%或绝对差异>10段
- 生成详细的翻译质量报告

#### 3. 成本跟踪系统
- 实时Token使用统计
- 自动成本计算（支持多种模型）
- 翻译完成后显示总成本和平均成本

#### 4. 术语表管理
- 自动维护和更新术语表
- 确保翻译一致性
- 支持预定义术语导入

## 🎯 最佳实践工作流程

### 推荐的完整翻译流程

```bash
# 1. 运行主翻译
python translator.py config.json

# 2. 查看翻译质量（注意控制台输出的警告信息）
# 寻找类似信息：⚠️ 批次9段落数量差异较大: 原文160段 vs 译文124段

# 3. 运行质量优化（强烈推荐）
python retranslate_batch.py --all-diff

# 4. 验证最终结果
python list_books.py --detailed  # 多书籍场景
```

### 质量指标说明

- **优秀**：段落差异 < 5%
- **良好**：段落差异 5-15%
- **需要优化**：段落差异 15-20%
- **必须重新翻译**：段落差异 > 20%

### 成本优化建议

1. **模型选择**：
   - `deepseek-v3`：性价比高，质量一般（推荐）
   - `gpt-4o`：质量最高，成本适中
   - `gpt-4`：质量很高，成本较高

2. **批次大小优化**：
   - 小文档：`pages_per_batch: 3-5`
   - 中等文档：`pages_per_batch: 5-8`
   - 大文档：`pages_per_batch: 8-12`

## ⚠️ 重要注意事项

### 使用前检查
1. **PDF质量**：确保PDF文件可以正确提取文本
2. **API配额**：确保API密钥有足够的配额
3. **网络稳定**：确保网络连接稳定
4. **磁盘空间**：确保有足够的磁盘空间存储输出文件

### 翻译过程中
1. **监控输出**：关注控制台的警告信息和段落数量对比
2. **及时优化**：发现问题批次后及时使用重新翻译工具
3. **成本控制**：启用成本跟踪，监控API使用情况

### 翻译完成后
1. **质量检查**：**必须运行** `retranslate_batch.py --all-diff` 进行质量优化
2. **结果验证**：检查最终文档的完整性和质量
3. **备份保存**：重要项目建议备份整个输出目录

## 🐛 故障排除

### 常见问题解决

**翻译质量问题**：
- 调整 `temperature` 参数（0.1-0.3）
- 使用重新翻译工具优化问题批次
- 检查术语表设置

**API调用问题**：
- 检查API密钥和配额
- 减少 `pages_per_batch` 值
- 检查网络连接

**文件处理问题**：
- 确保PDF文件路径正确
- 检查输出目录权限
- 验证文件编码格式

**成本控制**：
- 启用 `enable_cost_tracking` 监控成本
- 选择合适的模型和批次大小
- 使用重新翻译工具而非重新运行整个翻译

---

## 📚 相关文档

- `RETRANSLATE_GUIDE.md`：详细的重新翻译工具使用指南
- `config_example.json`：完整的配置文件示例
- `translation_report.txt`：翻译质量报告（翻译后生成）

**记住：translator.py 完成后，务必运行 retranslate_batch.py --all-diff 进行质量优化！**