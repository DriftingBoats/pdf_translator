# 重新翻译工具使用指南

当翻译过程中出现段落数量差异较大的批次时，可以使用以下工具进行重新翻译。

## 🔍 问题识别

在翻译日志中，如果看到类似以下警告信息：
```
[22:01:27] ⚠️  批次9段落数量差异较大: 原文160段 vs 译文124段
```

这表示该批次的翻译质量可能存在问题，需要重新翻译。

## 🛠️ 重新翻译工具

### 0. 书籍列表工具 (`list_books.py`)

**多本书场景必备**，用于查看和选择要处理的书籍。

```bash
# 列出所有书籍
python list_books.py

# 显示详细的质量分析
python list_books.py --detailed

# 直接指定输出目录
python list_books.py --output-dir ./my_output
```

### 1. 快速重新翻译工具 (`retranslate_batch.py`)

**推荐使用**，适合快速处理特定批次。

#### 基本用法

**交互式模式（推荐）：**
```bash
python retranslate_batch.py
```
运行后会显示交互式菜单：
```
🔄 重新翻译工具
==============================
请选择操作方式:
1. 重新翻译指定批次
2. 重新翻译所有差异较大的批次
3. 查看帮助信息
4. 退出

请输入选项 (1-4):
```

**命令行模式：**
```bash
# 重新翻译单个批次（单本书）
python retranslate_batch.py 9

# 重新翻译多个批次（单本书）
python retranslate_batch.py 9 12 15

# 重新翻译指定书籍的批次（多本书场景）
python retranslate_batch.py 9 --book-dir "output/book1"

# 自动重新翻译所有差异较大的批次
python retranslate_batch.py --all-diff

# 自动重新翻译指定书籍的所有问题批次（多本书场景）
python retranslate_batch.py --all-diff --book-dir "output/book1"

# 使用自定义配置文件
python retranslate_batch.py 9 --config my_config.json
```

#### 功能特点

- ✅ 快速启动，简洁输出
- ✅ 自动备份原翻译文件
- ✅ 支持批量处理
- ✅ 自动检测差异较大的批次
- ✅ 保持与主翻译脚本相同的翻译质量

### 2. 完整分析工具 (`retranslate_diff_batches.py`)

提供详细的分析和交互式操作。

#### 基本用法

**交互式模式（推荐）：**
```bash
python retranslate_diff_batches.py
```
运行后会显示交互式菜单：
```
🔄 重新翻译段落差异较大的批次
==================================================

请选择操作方式:
1. 分析并重新翻译差异较大的批次
2. 指定书籍目录进行分析
3. 查看帮助信息
4. 退出

请输入选项 (1-4):
```

**命令行模式：**
```bash
# 运行完整分析（单本书）
python retranslate_diff_batches.py --auto

# 分析指定书籍（多本书场景）
python retranslate_diff_batches.py --book-dir "output/book1"

# 使用自定义配置文件
python retranslate_diff_batches.py --config my_config.json --book-dir "output/book1"
```

#### 功能特点

- 📊 详细的批次差异分析
- 📝 完整的日志记录
- 🤝 交互式确认
- 📈 统计报告

## 📋 使用步骤

### 🔍 多本书场景：完整工作流程

#### 步骤1：查看所有书籍

```bash
# 列出所有书籍及其状态
python list_books.py --detailed
```

输出示例：
```
📚 在 output 中找到 3 本书:
================================================================================

1. 📖 novel_book1
   📁 路径: output/novel_book1
   📊 批次: 45/50 已完成
   📚 术语: 156 个条目
   📄 最终文档: ✅
   📈 完成率: 90.0%
   📉 平均段落差异: 8.5%
   ⚠️  问题批次: 3 个
      批次9: 160→124 (22.5%)
      批次15: 145→98 (32.4%)
      批次23: 178→142 (20.2%)
```

#### 步骤2：选择要处理的书籍和批次

从上面的输出中，我们看到 `novel_book1` 有3个问题批次。

#### 步骤3：重新翻译问题批次

**方式A：重新翻译指定批次**
```bash
python retranslate_batch.py 9 15 23 --book-dir "output/novel_book1"
```

**方式B：自动处理所有问题批次**
```bash
python retranslate_batch.py --all-diff --book-dir "output/novel_book1"
```

**方式C：使用完整分析工具**
```bash
python retranslate_diff_batches.py --book-dir "output/novel_book1"
```

### 🔍 单本书场景：传统流程

#### 步骤1：识别问题批次

从翻译日志中找到差异较大的批次号，例如：
```
⚠️  批次9段落数量差异较大: 原文160段 vs 译文124段
⚠️  批次15段落数量差异较大: 原文145段 vs 译文98段
```

#### 步骤2：选择重新翻译方式

**方式A：快速重新翻译指定批次**
```bash
python retranslate_batch.py 9 15
```

**方式B：自动处理所有问题批次**
```bash
python retranslate_batch.py --all-diff
```

**方式C：使用完整分析工具**
```bash
python retranslate_diff_batches.py
```

### 步骤3：验证结果

重新翻译完成后，检查日志输出：
```
✅ 批次 9 重新翻译完成
📝 翻译完成: 160 段 → 158 段
```

## ⚙️ 配置要求

确保 `config.json` 文件配置正确：

```json
{
  "api": {
    "API_URL": "https://api.openai.com/v1/chat/completions",
    "API_KEY": "your-api-key-here",
    "LLM_MODEL": "gpt-4o",
    "temperature": 0.2
  },
  "paths": {
    "pdf": "path/to/your/document.pdf",
    "output_dir": "output/document_name",
    "big_md_name": "translated_document.md"
  },
  "pages_per_batch": 10,
  "clean_cache_on_start": true,
  "verbose_logging": false
}
```

**注意**：重新翻译工具会自动从配置中读取以下信息：
- `api.API_KEY`：API密钥
- `api.API_URL`：API地址
- `api.LLM_MODEL`：使用的模型
- `paths.output_dir`：输出目录路径

## 📁 文件结构

重新翻译工具需要以下文件结构：

```
project/
├── config.json                    # 配置文件
├── retranslate_batch.py           # 快速重新翻译工具
├── retranslate_diff_batches.py    # 完整分析工具
├── list_books.py                  # 书籍列表工具
└── output/                        # 输出根目录
    ├── book1/                     # 单本书目录
    │   ├── chap_md/              # 翻译结果
    │   │   ├── batch_001.md      # 批次翻译文件
    │   │   ├── batch_002.md
    │   │   └── batch_009.md.backup  # 自动备份
    │   ├── raw_content/          # 原始内容
    │   │   ├── batch_001.txt     # 批次原始文本
    │   │   ├── batch_002.txt
    │   │   └── batch_009.txt
    │   ├── glossary.tsv          # 术语表
    │   └── final_document.md     # 最终合并文档（可选）
    └── book2/                     # 另一本书
        ├── chap_md/
        ├── raw_content/
        └── glossary.tsv
```

**书籍目录识别标准**：
- 必须包含 `chap_md/` 目录（翻译结果）
- 必须包含 `raw_content/` 目录（原始内容）
- 必须包含 `glossary.tsv` 文件（术语表）
- 至少满足其中2个条件才被识别为书籍目录

## 🔧 高级选项

### 自定义差异阈值

在 `retranslate_batch.py` 的 `find_diff_batches` 函数中，可以修改差异检测阈值：

```python
def find_diff_batches(output_dir: Path, threshold: float = 0.2) -> List[int]:
    # 默认阈值：差异超过20%或绝对差异超过10个段落
    if diff_ratio > threshold or abs(original_segments - translated_segments) > 10:
```

在 `retranslate_diff_batches.py` 中也有类似的阈值设置：

```python
# 如果差异超过20%或绝对差异超过10个段落，标记为问题批次
if diff_ratio > 0.2 or abs(original_segments - translated_segments) > 10:
```

### 批量处理优化

- 工具会在API调用之间自动添加2秒延迟
- 避免触发API限制
- 可根据需要调整延迟时间

## ⚠️ 注意事项

1. **备份保护**：原翻译文件会自动备份为 `.backup` 文件
2. **API消耗**：重新翻译会消耗API调用次数
3. **网络要求**：需要稳定的网络连接
4. **文件权限**：确保有写入输出目录的权限

## 🐛 故障排除

### 常见问题

**问题1：找不到配置文件**
```
❌ 配置文件 config.json 不存在
```
**解决**：确保 `config.json` 文件存在且格式正确，参考 `config_example.json`

**问题2：找不到批次文件**
```
❌ 批次 9 原始文件不存在
```
**解决**：
- 确保已运行过主翻译脚本 `translator.py`，生成了 `raw_content/batch_009.txt` 文件
- 检查指定的书籍目录是否存在
- 确认批次号是否正确（使用 `retranslate_diff_batches.py` 查看可用批次）

**问题3：找不到书籍目录**
```
❌ 输出目录不存在: output/book1
```
**解决**：使用 `list_books.py` 查看可用的书籍目录，或检查 `--book-dir` 参数路径

**问题4：目录路径包含空格**
```
❌ retranslate_batch.py: error: unrecognized arguments: love feelings
```
**解决**：使用引号包围包含空格的路径
```bash
# ❌ 错误写法
python retranslate_batch.py 9 --book-dir output/bake love feelings

# ✅ 正确写法
python retranslate_batch.py 9 --book-dir "output/bake love feelings"

# 或者使用交互式模式（推荐）
python retranslate_batch.py
```

**问题5：API调用失败**
```
❌ 批次 9 翻译失败: timeout
```
**解决**：检查网络连接、API密钥和配置中的 `api.API_URL` 设置

**问题6：无法识别书籍目录**
```
📚 在 output 中未找到任何书籍目录
```
**解决**：确保目录包含 `chap_md/`、`raw_content/` 和 `glossary.tsv` 中的至少2个

### 日志文件

- **控制台输出**：实时处理状态，使用彩色日志和表情符号
- **自动备份**：原翻译文件自动备份为 `.backup` 扩展名
- **详细统计**：显示处理进度和成功率

## 🎯 交互式操作模式

重新翻译工具现在支持**交互式操作模式**，让使用更加友好：

### 功能特性

- **智能引导**：无需记忆复杂的命令行参数
- **错误防护**：输入验证和友好的错误提示
- **灵活选择**：支持多种操作模式的快速切换
- **用户友好**：清晰的菜单和操作提示

### 使用方法

**启动交互式模式：**
```bash
# 重新翻译工具
python retranslate_batch.py

# 完整分析工具
python retranslate_diff_batches.py
```

**交互式流程：**
1. **选择操作** → 从菜单中选择要执行的操作
2. **输入参数** → 根据提示输入必要的参数
3. **确认执行** → 系统会显示将要执行的操作
4. **查看结果** → 实时显示处理进度和结果

### 优势对比

| 模式 | 优势 | 适用场景 |
|------|------|----------|
| **交互式** | 用户友好、防错、引导式 | 新手用户、偶尔使用 |
| **命令行** | 快速、可脚本化、批处理 | 熟练用户、自动化场景 |

## 🔄 自动合并功能

重新翻译工具现在支持**自动合并markdown文件**功能：

### 功能特性

- **智能检测**：自动识别单书籍或多书籍场景
- **自动触发**：重新翻译成功后自动执行合并
- **路径适配**：支持 `chap_md/` 目录和直接输出目录
- **错误处理**：合并失败时提供清晰的错误信息

### 工作流程

1. **重新翻译完成** → 检查是否有成功的批次
2. **自动检测结构** → 判断是否为多书籍场景
3. **收集文件** → 从相应目录收集所有 `.md` 文件
4. **按序合并** → 按文件名排序后合并内容
5. **生成最终文档** → 输出到配置指定的路径

### 支持场景

**单书籍场景：**
```
output/
├── batch_001.md
├── batch_002.md
└── translated_document.md  ← 自动生成
```

**多书籍场景：**
```
output/book1/
├── chap_md/
│   ├── batch_001.md
│   └── batch_002.md
└── translated_document.md  ← 自动生成
```

## 📊 效果评估

重新翻译后，段落数量差异应该显著减少：

**重新翻译前：**
```
[22:01:27] ⚠️  批次9段落数量差异较大: 原文160段 vs 译文124段
```

**重新翻译后：**
```
[22:05:43] 📝 翻译完成: 160 段 → 158 段
[22:05:43] ✅ 批次 9 重新翻译完成
```

**自动合并输出：**
```
[22:05:45] 📚 正在重新生成整书markdown文件...
[22:05:45] 📝 开始合并 25 个markdown文件...
[22:05:46] ✅ 已生成整书 Markdown：output/book1/translated_document.md
[22:05:46] 🎊 整书markdown文件已更新!
```

**质量分析输出：**
```
📉 平均段落差异: 2.1%
⚠️  问题批次: 0 个
```

## 🎯 最佳实践

1. **及时处理**：发现差异较大的批次后尽快重新翻译
2. **批量处理**：使用 `--all-diff` 选项一次性处理所有问题批次
3. **验证结果**：重新翻译后检查段落数量是否合理
4. **保留备份**：重要项目建议手动备份整个输出目录

---

通过这些工具，您可以有效地解决翻译过程中的段落对齐问题，确保翻译质量的一致性。