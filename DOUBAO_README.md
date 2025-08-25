# 豆包翻译脚本使用说明

## 概述

`translator_doubao.py` 是基于原始翻译脚本修改的版本，专门适配豆包（Doubao）大模型API。该脚本保持了原有的所有翻译功能和要求，仅将API调用部分修改为豆包格式。

## 主要特性

- ✅ 使用豆包 `doubao-seed-1-6` 模型
- ✅ 保持原有翻译质量和格式要求
- ✅ 支持PDF裁切功能
- ✅ 批量处理和缓存机制
- ✅ 成本跟踪和统计
- ✅ 失败重试机制

## 配置文件

使用 `config_doubao.json` 作为配置文件模板：

```json
{
  "api": {
    "API_URL": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "API_KEY": "your-doubao-api-key-here",
    "LLM_MODEL": "doubao-seed-1-6-250615",
    "temperature": 0.5
  },
  "pricing": {
    "input_price_per_1k_tokens": 0.0008,
    "output_price_per_1k_tokens": 0.008,
    "currency": "CNY",
    "enable_cost_tracking": true
  },
  "paths": {
    "pdf": "your_document.pdf",
    "output_dir": "output/your_output",
    "big_md_name": "translated_document.md"
  },
  "pages_per_batch": 8,
  "clean_cache_on_start": false,
  "pdf_crop": {
    "enable": false,
    "auto_detect_headers": true,
    "margins": {
      "top": 50,
      "bottom": 50,
      "left": 30,
      "right": 30
    }
  }
}
```

## 使用方法

### 1. 配置API密钥

在 `config_doubao.json` 中设置你的豆包API密钥：

```json
"API_KEY": "your-actual-doubao-api-key"
```

### 2. 设置文件路径

修改配置文件中的路径：

```json
"paths": {
  "pdf": "path/to/your/document.pdf",
  "output_dir": "output/your_project_name",
  "big_md_name": "final_translation.md"
}
```

### 3. 运行翻译

```bash
python3 translator_doubao.py config_doubao.json
```

## API请求格式

脚本使用以下格式调用豆包API（已根据官方文档优化）：

```json
{
  "model": "doubao-seed-1-6-250615",
  "messages": [
    {
      "role": "system",
      "content": "系统提示词..."
    },
    {
      "role": "user",
      "content": "待翻译文本..."
    }
  ],
  "temperature": 0.5,
  "thinking": false,
  "max_completion_tokens": 8000,
  "stream": false
}
```

## 与原版差异

1. **API调用格式**：适配豆包API的请求格式，根据官方文档优化
2. **模型名称**：使用 `doubao-seed-1-6-250615`（完整版本号）
3. **性能优化**：
   - 关闭深度思考模式（`thinking: false`）以提高翻译速度
   - 设置输出长度限制（`max_completion_tokens: 8000`）
   - 禁用流式输出（`stream: false`）
4. **定价更新**：根据官方定价调整成本计算
5. **其他功能**：完全保持原有功能不变

## 注意事项

- 确保豆包API密钥有效且有足够额度
- 豆包API的定价可能与OpenAI不同，请根据实际情况调整配置
- 网络连接需要能够访问豆包API服务
- 建议先用小文档测试配置是否正确

## 故障排除

1. **API密钥错误**：检查配置文件中的API_KEY是否正确
2. **网络连接问题**：确认能够访问豆包API服务
3. **文件路径错误**：检查PDF文件路径和输出目录是否正确
4. **权限问题**：确保有读取PDF和写入输出目录的权限

## 支持

如有问题，请检查：
1. 配置文件格式是否正确
2. API密钥是否有效
3. 网络连接是否正常
4. 文件路径是否存在