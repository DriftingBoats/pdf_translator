# PDF裁切命令行工具使用说明

## 概述

`pdf_crop_cli.py` 是一个交互式命令行工具，用于可视化地确定PDF裁切参数。当图形界面工具无法正常显示时，这个命令行版本提供了同样强大的功能。

## 🚀 快速开始

### 启动工具

```bash
# 直接启动
python3 pdf_crop_cli.py

# 或者直接加载PDF文件
python3 pdf_crop_cli.py your_document.pdf
```

### 基本使用流程

1. **加载PDF文件**
   ```
   > load /path/to/your/document.pdf
   ```

2. **分析页面布局**
   ```
   > analyze 1
   ```
   工具会自动检测页眉页脚并给出建议的裁切参数

3. **调整裁切参数**
   ```
   > adjust
   ```
   交互式输入各边距值

4. **预览裁切效果**
   ```
   > preview
   ```
   查看裁切后的页面尺寸

5. **应用裁切**
   ```
   > apply
   ```
   生成裁切后的PDF文件

## 📖 详细命令说明

### 文件操作

- **`load <pdf_path>`** - 加载PDF文件
  ```
  > load document.pdf
  > load /Users/username/Documents/paper.pdf
  ```

### 分析功能

- **`analyze [page_num]`** - 分析页面布局
  ```
  > analyze        # 分析第1页
  > analyze 3      # 分析第3页
  ```
  
  分析结果包括：
  - 📐 页面尺寸
  - 📝 文本块数量
  - 📋 检测到的页眉页脚
  - 💡 建议的裁切参数

### 参数调整

- **`adjust`** - 交互式调整边距
  ```
  > adjust
  🎛️  调整裁切边距 (输入数字，回车确认，直接回车跳过):
     顶部边距 (当前: 0px): 50
     底部边距 (当前: 0px): 50
     左侧边距 (当前: 0px): 30
     右侧边距 (当前: 0px): 30
  ```

- **`show`** - 显示当前设置
  ```
  > show
  ⚙️  当前裁切设置:
     顶部边距: 50px
     底部边距: 50px
     左侧边距: 30px
     右侧边距: 30px
  ```

### 预览和应用

- **`preview`** - 预览裁切效果
  ```
  > preview
  🔍 裁切预览:
     将从PDF的每一页裁切掉:
     • 顶部 50px
     • 底部 50px
     • 左侧 30px
     • 右侧 30px
  
  📐 裁切后页面尺寸:
     原始: 595.0 x 842.0
     裁切后: 535.0 x 742.0
  ```

- **`apply`** - 应用裁切
  ```
  > apply
  🔄 正在应用裁切...
  ✅ 裁切完成！
  📁 输出文件: document_cropped.pdf
  ```

### 配置管理

- **`save [config_path]`** - 保存配置
  ```
  > save                    # 保存到默认文件
  > save my_crop_config.json # 保存到指定文件
  ```

- **`load_config [config_path]`** - 加载配置
  ```
  > load_config my_crop_config.json
  ```

### 其他命令

- **`help`** - 显示帮助信息
- **`quit`** / **`exit`** / **`q`** - 退出程序

## 💡 使用技巧

### 1. 智能分析

工具的 `analyze` 命令会自动检测页眉页脚：

```
> analyze 1
📊 页面 1 布局分析:
📐 页面尺寸: 595.0 x 842.0
📝 文本块数量: 15
📋 检测到页眉: y=50.0-70.0, 内容='Chapter 1: Introduction...'
📋 检测到页脚: y=800.0-820.0, 内容='Page 1...'

💡 建议裁切参数:
   顶部: 70.0px
   底部: 42.0px
   左侧: 30.0px
   右侧: 30.0px

🤔 是否应用建议的裁切参数? (y/n): y
✅ 已应用建议的裁切参数
```

### 2. 批量处理工作流

```bash
# 1. 分析文档确定参数
python3 pdf_crop_cli.py sample.pdf
> analyze
> adjust
> save standard_crop.json
> quit

# 2. 应用到其他文档
python3 pdf_crop_cli.py document1.pdf
> load_config standard_crop.json
> apply
> quit
```

### 3. 配置文件格式

保存的配置文件可以直接用于翻译脚本：

```json
{
  "pdf_crop": {
    "enable": true,
    "margins": {
      "top": 50,
      "bottom": 50,
      "left": 30,
      "right": 30
    }
  }
}
```

## 🔧 与翻译脚本集成

### 步骤1：确定裁切参数

```bash
python3 pdf_crop_cli.py your_document.pdf
> analyze
> adjust  # 根据需要微调
> save crop_config.json
```

### 步骤2：应用到翻译配置

将生成的配置文件内容复制到翻译脚本的配置文件中，或者直接使用：

```bash
# 使用Doubao翻译脚本
python3 translator_doubao.py --config crop_config.json
```

## 🎯 实际应用示例

### 学术论文处理

```
> load research_paper.pdf
> analyze 1
📋 检测到页眉: y=50.0-70.0, 内容='Journal of Computer Science...'
📋 检测到页脚: y=800.0-820.0, 内容='Vol. 15, No. 3, 2024...'

> adjust
   顶部边距 (当前: 0px): 70
   底部边距 (当前: 0px): 50
   左侧边距 (当前: 0px): 40
   右侧边距 (当前: 0px): 40

> preview
📐 裁切后页面尺寸:
   原始: 595.0 x 842.0
   裁切后: 515.0 x 722.0

> save academic_paper_crop.json
> apply
```

### 技术文档处理

```
> load manual.pdf
> analyze 1
💡 建议裁切参数:
   顶部: 60.0px
   底部: 40.0px
   左侧: 35.0px
   右侧: 35.0px

🤔 是否应用建议的裁切参数? (y/n): y
> preview
> apply
```

## ⚠️ 注意事项

1. **参数验证**：工具会检查裁切参数是否会导致内容丢失
2. **文件备份**：原始PDF文件不会被修改，裁切结果保存为新文件
3. **页面一致性**：建议检查多个页面确保裁切效果一致
4. **配置复用**：相同类型的文档可以复用配置文件

## 🔍 故障排除

### 常见问题

**Q: 无法检测到页眉页脚**
A: 某些PDF的页眉页脚可能是图像格式，工具主要检测文本内容

**Q: 裁切后内容丢失**
A: 检查边距设置是否过大，使用 `preview` 命令查看裁切后尺寸

**Q: 配置文件格式错误**
A: 确保JSON格式正确，可以使用工具的 `save` 命令生成标准格式

### 调试模式

如果遇到问题，可以查看详细的分析信息：

```
> analyze 1
# 查看检测到的文本块和布局信息
```

## 📝 总结

命令行版本的PDF裁切工具提供了与图形界面相同的功能：

- ✅ 智能页眉页脚检测
- ✅ 交互式参数调整
- ✅ 实时预览效果
- ✅ 配置文件管理
- ✅ 与翻译脚本集成

当图形界面无法正常显示时，这个命令行版本是完美的替代方案！