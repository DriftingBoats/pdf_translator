#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translator_doubao.py
—— 使用豆包(doubao-seed-1-6)模型的PDF翻译脚本
  • 按指定页数X自动分批翻译
  • 处理句子完整性，确保翻译至句子结束
  • 自动识别标题并保持格式
  • 自动编号并最终整合为一个文件
  • 使用prompt约束专有名词处理
  • 适配豆包API格式
"""
import json, re, textwrap, logging, time, datetime, requests, os, sys, warnings, random
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 过滤PyMuPDF的警告信息
warnings.filterwarnings("ignore", category=UserWarning, module="fitz")

import fitz  # PyMuPDF - pip install PyMuPDF
from pdf_crop_tool import PDFCropTool  # 导入PDF裁切工具

# 成本跟踪全局变量
total_cost = 0.0
total_input_tokens = 0
total_output_tokens = 0

# ========= 缓存管理功能 ========= #
def clean_cache_files(cache_dir: Path, pdf_path: Path = None, force: bool = False):
    """清理缓存文件
    
    Args:
        cache_dir: 缓存目录
        pdf_path: PDF文件路径，用于检查缓存是否过期
        force: 是否强制清理所有缓存
    """
    if not cache_dir.exists():
        return
    
    cache_patterns = [
        "*_text_cache.txt",      # PDF文本缓存
        "batch_*_raw_text.txt",  # 批次文本缓存
    ]
    
    cleaned_count = 0
    total_size_cleaned = 0
    
    logging.info(f"🧹 开始清理缓存文件 (强制清理: {'是' if force else '否'})")
    
    for pattern in cache_patterns:
        for cache_file in cache_dir.glob(pattern):
            should_clean = force
            
            if not should_clean and pdf_path and pdf_path.exists():
                try:
                    # 检查缓存是否过期
                    pdf_mtime = pdf_path.stat().st_mtime
                    cache_mtime = cache_file.stat().st_mtime
                    should_clean = cache_mtime < pdf_mtime
                except Exception:
                    should_clean = True  # 出错时清理
            
            if should_clean:
                try:
                    file_size = cache_file.stat().st_size
                    cache_file.unlink()
                    cleaned_count += 1
                    total_size_cleaned += file_size
                    logging.info(f"🗑️  删除过期缓存: {cache_file.name} ({file_size/1024:.1f}KB)")
                except Exception as e:
                    logging.warning(f"⚠️  清理缓存文件失败 {cache_file}: {e}")
    
    if cleaned_count > 0:
        logging.info(f"✅ 缓存清理完成: 删除 {cleaned_count} 个文件，释放 {total_size_cleaned/1024:.1f}KB 空间")
    else:
        logging.info("💾 无需清理缓存文件")

# ========= 读取配置 ========= #
def load_config(config_file: str = None) -> Dict:
    """安全加载配置文件"""
    ROOT = Path(__file__).resolve().parent
    
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = ROOT / config_file
    else:
        # 如果没有指定配置文件，尝试从命令行参数获取
        if len(sys.argv) > 1:
            config_path = Path(sys.argv[1])
            if not config_path.is_absolute():
                config_path = ROOT / sys.argv[1]
        else:
            # 默认使用当前目录下的config.json
            config_path = ROOT / "config.json"
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        
        # 验证必需的配置项
        required_keys = ["api", "paths"]
        for key in required_keys:
            if key not in config:
                raise KeyError(f"配置文件缺少必需的键: {key}")
        
        # 验证API配置
        api_config = config["api"]
        required_api_keys = ["API_URL", "API_KEY", "LLM_MODEL"]
        for key in required_api_keys:
            if key not in api_config:
                raise KeyError(f"API配置缺少必需的键: {key}")
        
        # 验证路径配置
        paths_config = config["paths"]
        required_path_keys = ["pdf", "output_dir"]
        for key in required_path_keys:
            if key not in paths_config:
                raise KeyError(f"路径配置缺少必需的键: {key}")
        
        logging.info(f"✅ 配置文件加载成功: {config_path}")
        return config
        
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件JSON格式错误: {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置文件失败: {e}")

# ========= 配置加载和验证 ========= #
try:
    CONFIG = load_config()
except Exception as e:
    print(f"❌ 配置加载失败: {e}")
    print("\n请选择配置文件:")
    print("1. 使用默认配置 (config.json)")
    print("2. 输入自定义配置文件路径")
    
    choice = input("请输入选择 (1/2): ").strip()
    
    if choice == "1":
        try:
            CONFIG = load_config("config.json")
        except Exception as e:
            print(f"❌ 默认配置加载失败: {e}")
            sys.exit(1)
    elif choice == "2":
        config_path = input("请输入配置文件路径: ").strip()
        try:
            CONFIG = load_config(config_path)
        except Exception as e:
            print(f"❌ 自定义配置加载失败: {e}")
            sys.exit(1)
    else:
        print("❌ 无效选择")
        sys.exit(1)

# 提取配置
API_URL = CONFIG["api"]["API_URL"]
API_KEY = CONFIG["api"]["API_KEY"]
LLM_MODEL = CONFIG["api"]["LLM_MODEL"]
TEMPERATURE = CONFIG["api"].get("temperature", 0.2)

PDF_PATH = Path(CONFIG["paths"]["pdf"])
OUT_DIR = Path(CONFIG["paths"]["output_dir"])
BIG_MD_NAME = CONFIG["paths"].get("big_md_name", "translated_document.md")

PAGES_PER_BATCH = CONFIG.get("pages_per_batch", 8)

# PDF裁切配置
PDF_CROP_CONFIG = CONFIG.get("pdf_crop", {})
ENABLE_PDF_CROP = PDF_CROP_CONFIG.get("enable", False)
CROP_MARGINS = PDF_CROP_CONFIG.get("margins", {"top": 50, "bottom": 50, "left": 30, "right": 30})
AUTO_DETECT_HEADERS = PDF_CROP_CONFIG.get("auto_detect_headers", True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(OUT_DIR / "translation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 验证文件路径
if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF文件不存在: {PDF_PATH}")

logging.info(f"=== 豆包PDF翻译器启动 ===")
logging.info(f"PDF文件: {PDF_PATH}")
logging.info(f"输出目录: {OUT_DIR}")
logging.info(f"模型: {LLM_MODEL}")
logging.info(f"每批页数: {PAGES_PER_BATCH}")
logging.info(f"PDF裁切: {'启用' if ENABLE_PDF_CROP else '禁用'}")

# 创建输出目录
try:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHAP_DIR = OUT_DIR / "chap_md"
    CHAP_DIR.mkdir(exist_ok=True)
    RAW_CONTENT_DIR = OUT_DIR / "raw_content"
    RAW_CONTENT_DIR.mkdir(exist_ok=True)
    logging.info(f"输出目录已准备: {OUT_DIR}")
    logging.info(f"原始内容目录已准备: {RAW_CONTENT_DIR}")
except Exception as e:
    raise RuntimeError(f"创建输出目录失败: {e}")

# 清理缓存
if CONFIG.get("clean_cache_on_start", True):
    logging.info("=== 检查并清理过期缓存文件 ===")
    clean_cache_files(RAW_CONTENT_DIR, PDF_PATH, force=False)

# 术语表处理（保持原有逻辑）
logging.info("术语表功能已禁用，使用prompt约束专有名词处理")

# ========= PDF文本提取 ========= #
def get_pdf_text_with_cache(pdf_path: Path, cache_dir: Path) -> str:
    """从PDF提取文本，支持缓存和裁切功能"""
    cache_file = cache_dir / f"{pdf_path.stem}_text_cache.txt"
    
    # 检查缓存
    if cache_file.exists():
        try:
            pdf_mtime = pdf_path.stat().st_mtime
            cache_mtime = cache_file.stat().st_mtime
            
            if cache_mtime >= pdf_mtime:
                logging.info(f"💾 使用PDF文本缓存: {cache_file.name}")
                return cache_file.read_text(encoding="utf-8")
            else:
                logging.info(f"🔄 PDF文件已更新，重新提取文本")
        except Exception as e:
            logging.warning(f"检查缓存时间戳失败: {e}，重新提取")
    
    logging.info(f"📖 开始提取PDF文本: {pdf_path.name}")
    
    try:
        doc = fitz.open(pdf_path)
        all_text = []
        
        # 初始化PDF裁切工具
        crop_tool = None
        if ENABLE_PDF_CROP:
            try:
                crop_tool = PDFCropTool(str(pdf_path))
                if AUTO_DETECT_HEADERS:
                    logging.info("🔍 自动检测页眉页脚并裁切")
                    crop_tool.auto_crop_headers_footers()
                else:
                    logging.info(f"✂️  手动裁切边距: {CROP_MARGINS}")
                    crop_tool.crop_pages(**CROP_MARGINS)
            except Exception as e:
                logging.warning(f"PDF裁切初始化失败，使用原始页面: {e}")
                crop_tool = None
        
        for page_num in range(len(doc)):
            try:
                page = doc[page_num]
                
                # 如果启用了裁切，使用裁切后的页面
                if crop_tool:
                    try:
                        # 获取裁切后的文本
                        blocks = page.get_text("blocks", sort=True)
                        page_text = "\n".join([block[4] for block in blocks if block[4].strip()])
                    except Exception as e:
                        logging.warning(f"页面{page_num+1}裁切失败，使用原始文本: {e}")
                        page_text = page.get_text("blocks", sort=True)
                        page_text = "\n".join([block[4] for block in page_text if block[4].strip()])
                else:
                    # 使用原始页面
                    blocks = page.get_text("blocks", sort=True)
                    page_text = "\n".join([block[4] for block in blocks if block[4].strip()])
                
                all_text.append(page_text)
                
            except Exception as e:
                logging.error(f"提取第{page_num+1}页文本失败: {e}")
                all_text.append("")
        
        # 关闭裁切工具
        if crop_tool:
            try:
                crop_tool.close()
            except Exception as e:
                logging.warning(f"关闭PDF裁切工具失败: {e}")
        
        doc.close()
        
        # 合并所有页面文本，使用\f分隔
        full_text = "\f".join(all_text)
        
        # 保存缓存
        try:
            cache_file.write_text(full_text, encoding="utf-8")
            logging.info(f"💾 PDF文本已缓存: {cache_file.name}")
        except Exception as e:
            logging.warning(f"保存PDF文本缓存失败: {e}")
        
        logging.info(f"✅ PDF文本提取完成，总长度: {len(full_text)} 字符")
        return full_text
        
    except Exception as e:
        raise RuntimeError(f"PDF文本提取失败: {e}")

# ========= 豆包API调用 ========= #
def call_llm(prompt_sys: str, prompt_user: str, max_retries: int = 3, timeout: int = 120) -> str:
    """调用豆包LLM API，带重试和错误处理"""
    global total_cost, total_input_tokens, total_output_tokens
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 豆包API格式 - 根据官方文档优化
    payload = {
        "model": "doubao-seed-1-6-250615",
        "messages": [
            {"role": "system", "content": prompt_sys},
            {"role": "user", "content": prompt_user}
        ],
        "temperature": TEMPERATURE,
        "thinking": False,  # 关闭深度思考模式以提高翻译速度
        "max_completion_tokens": 8000,  # 限制输出长度
        "stream": False
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logging.info(f"🤖 调用豆包API - 模型: doubao-seed-1-6 (尝试 {attempt+1}/{max_retries})")
            logging.debug(f"系统提示长度: {len(prompt_sys)} 字符")
            logging.debug(f"用户输入长度: {len(prompt_user)} 字符")
            
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            
            result = resp.json()
            if "choices" not in result or not result["choices"]:
                raise ValueError("API返回格式错误：缺少choices字段")
            
            content = result["choices"][0]["message"]["content"]
            if not content or not content.strip():
                raise ValueError("API返回内容为空")
            
            logging.info(f"✅ 豆包响应成功 - 输出长度: {len(content)} 字符")
            
            # 记录token使用情况和计算成本
            if "usage" in result and result["usage"]:
                usage = result["usage"]
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                # 累计token统计
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                
                # 计算成本（如果启用了成本跟踪）
                if CONFIG.get('pricing', {}).get('enable_cost_tracking', False):
                    pricing = CONFIG.get('pricing', {})
                    input_price_per_1k = pricing.get('input_price_per_1k_tokens', 0)
                    output_price_per_1k = pricing.get('output_price_per_1k_tokens', 0)
                    currency = pricing.get('currency', 'USD')
                    
                    batch_input_cost = (input_tokens / 1000) * input_price_per_1k
                    batch_output_cost = (output_tokens / 1000) * output_price_per_1k
                    batch_total_cost = batch_input_cost + batch_output_cost
                    
                    total_cost += batch_total_cost
                    
                    logging.info(f"📊 Token使用: 输入{input_tokens} + 输出{output_tokens} = 总计{total_tokens}")
                    logging.info(f"💰 本次成本: {batch_total_cost:.4f} {currency} (输入: {batch_input_cost:.4f} + 输出: {batch_output_cost:.4f})")
                    logging.info(f"💳 累计成本: {total_cost:.4f} {currency}")
                else:
                    logging.info(f"📊 Token使用: 输入{input_tokens} + 输出{output_tokens} = 总计{total_tokens}")
            
            return content.strip()
            
        except requests.exceptions.Timeout:
            last_error = f"请求超时({timeout}秒)"
            logging.warning(f"豆包API调用超时({attempt+1}/{max_retries})")
        except requests.exceptions.ConnectionError:
            last_error = "网络连接错误"
            logging.warning(f"豆包API调用网络错误({attempt+1}/{max_retries})")
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP错误: {e.response.status_code}"
            logging.warning(f"豆包API调用HTTP错误({attempt+1}/{max_retries}): {e}")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            last_error = f"响应解析错误: {e}"
            logging.warning(f"豆包API调用解析错误({attempt+1}/{max_retries}): {e}")
        except Exception as e:
            last_error = f"未知错误: {e}"
            logging.warning(f"豆包API调用未知错误({attempt+1}/{max_retries}): {e}")
        
        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 2
            logging.info(f"⏳ 等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
    
    raise RuntimeError(f"豆包API调用失败，已重试{max_retries}次: {last_error}")

# ========= 其他辅助函数 ========= #
def log_progress(current: int, total: int, task_name: str, current_info: str = "", start_time: float = None):
    """记录进度信息"""
    percentage = (current / total) * 100 if total > 0 else 0
    progress_bar = "█" * int(percentage // 5) + "░" * (20 - int(percentage // 5))
    
    time_info = ""
    if start_time:
        elapsed = time.time() - start_time
        if current > 0:
            avg_time = elapsed / current
            remaining = (total - current) * avg_time
            time_info = f" | 已用时: {elapsed/60:.1f}分钟 | 预计剩余: {remaining/60:.1f}分钟"
    
    logging.info(f"📊 {task_name}: [{progress_bar}] {percentage:.1f}% ({current}/{total}){time_info} {current_info}")

def ensure_sentence_completion_optimized(text: str, next_batch_preview: str = "", max_supplement: int = 50) -> str:
    """优化的句子完整性处理，限制补充字符数量"""
    if not text or not text.strip():
        return text
    
    # 检查文本是否以句子结束符结尾
    sentence_endings = ['.', '!', '?', '。', '！', '？', '\n\n']
    
    # 如果已经以句子结束符结尾，直接返回
    if any(text.rstrip().endswith(ending) for ending in sentence_endings):
        return text
    
    # 如果没有下一批次预览文本，添加句号
    if not next_batch_preview:
        return text + "."
    
    # 限制搜索范围，避免过度读取
    search_text = next_batch_preview[:max_supplement]
    
    # 查找最近的句子结束位置
    best_pos = -1
    best_ending = ""
    
    for ending in sentence_endings:
        pos = search_text.find(ending)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
            best_ending = ending
    
    # 如果找到句子结束符，补充到该位置
    if best_pos != -1:
        supplement = search_text[:best_pos + len(best_ending)]
        logging.info(f"📝 句子完整性处理: 补充 {len(supplement)} 字符")
        return text + supplement
    
    # 如果没有找到明确的句子结束符，添加句号
    logging.info("📝 句子完整性处理: 未找到句子结束符，添加句号")
    return text + "."

# 使用优化后的函数
ensure_sentence_completion = ensure_sentence_completion_optimized

def wrap_batch_with_tags(text: str) -> str:
    """为批次文本添加段落标签"""
    if not text or not text.strip():
        return text
    
    # 按段落分割（双换行符或单换行符）
    paragraphs = re.split(r'\n\s*\n|\n', text)
    
    # 过滤空段落
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return text
    
    # 添加标签
    tagged_paragraphs = []
    for i, paragraph in enumerate(paragraphs, 1):
        tagged_paragraphs.append(f"<c{i}>{paragraph}</c{i}>")
    
    return "\n\n".join(tagged_paragraphs)

def refresh_style(sample_text: str) -> str:
    """分析文本风格"""
    global style_cache
    
    if not sample_text or len(sample_text) < 100:
        style_cache = ""
        return style_cache
    
    # 简单的风格分析
    style_indicators = []
    
    # 检查对话比例
    dialogue_count = len(re.findall(r'["""\'\'\'].*?["""\'\'\']', sample_text))
    total_sentences = len(re.findall(r'[.!?。！？]', sample_text))
    
    if total_sentences > 0:
        dialogue_ratio = dialogue_count / total_sentences
        if dialogue_ratio > 0.3:
            style_indicators.append("对话较多")
        elif dialogue_ratio > 0.1:
            style_indicators.append("适量对话")
        else:
            style_indicators.append("叙述为主")
    
    # 检查句子长度
    sentences = re.split(r'[.!?。！？]', sample_text)
    avg_length = sum(len(s.strip()) for s in sentences if s.strip()) / max(len([s for s in sentences if s.strip()]), 1)
    
    if avg_length > 50:
        style_indicators.append("长句较多")
    elif avg_length > 25:
        style_indicators.append("句子适中")
    else:
        style_indicators.append("短句为主")
    
    style_cache = f"，文本特征：{', '.join(style_indicators)}"
    logging.info(f"📝 文本风格分析: {style_cache}")
    return style_cache

# 初始化风格缓存
style_cache = ""

# ========= 主要处理逻辑 ========= #

# 加载PDF
logging.info(f"开始加载PDF文件: {PDF_PATH}")
try:
    # 提取PDF文本
    full_text = get_pdf_text_with_cache(PDF_PATH, RAW_CONTENT_DIR)
    if not full_text or not full_text.strip():
        raise ValueError("PDF文件内容为空或无法提取文本")
    
    pages = re.split(r"\f", full_text)                           # PyMuPDF 按 formfeed 分页
    if pages and pages[-1] == "":
        pages.pop()
    
    logging.info(f"PDF加载完成，共{len(pages)}页")
    
    # 验证分批设置
    max_page = len(pages)
    if PAGES_PER_BATCH < 1:
        raise ValueError(f"每批页数必须大于0，当前设置: {PAGES_PER_BATCH}")
    
    logging.info(f"将按每{PAGES_PER_BATCH}页进行分批翻译，PDF共{max_page}页")
    
except Exception as e:
    raise RuntimeError(f"PDF处理失败: {e}")

# 初始化处理变量
MISSING_DICT = {}
WARNING_DICT = {}  # 收集段落数量差异等警告信息
big_md_parts = []
total_pages = len(pages)
total_batches = (total_pages + PAGES_PER_BATCH - 1) // PAGES_PER_BATCH  # 向上取整
processed_batches = 0

logging.info(f"=== 开始分批翻译处理 ===")
logging.info(f"总批次: {total_batches} | 每批页数: {PAGES_PER_BATCH} | 总页数: {total_pages}")

# 开始计时
batch_start_time = time.time()

def get_batch_text_with_cache(pages: List[str], batch_num: int, p_start: int, p_end: int, cache_dir: Path) -> str:
    """获取批次文本，支持缓存"""
    batch_id = f"batch_{batch_num:03d}"
    cache_file = cache_dir / f"{batch_id}_raw_text.txt"
    
    # 检查缓存
    if cache_file.exists():
        try:
            cached_text = cache_file.read_text(encoding="utf-8")
            if cached_text.strip():
                logging.info(f"💾 使用批次文本缓存: {batch_id}")
                return cached_text
        except Exception as e:
            logging.warning(f"读取批次文本缓存失败: {e}，重新生成")
    
    # 生成批次文本
    batch_pages = pages[(p_start-1):p_end]  # 转换为0索引
    batch_text = "\n\n".join(batch_pages)
    
    # 保存缓存
    try:
        cache_file.write_text(batch_text, encoding="utf-8")
        logging.info(f"💾 批次文本已缓存: {batch_id}")
    except Exception as e:
        logging.warning(f"保存批次文本缓存失败: {e}")
    
    return batch_text

# 分批处理
for batch_num in range(1, total_batches + 1):
    processed_batches += 1
    
    # 计算页面范围
    p_start = (batch_num - 1) * PAGES_PER_BATCH + 1
    p_end = min(batch_num * PAGES_PER_BATCH, total_pages)
    
    # 记录进度
    logging.info(f"=== 处理批次 {batch_num}/{total_batches} (页 {p_start}-{p_end}) ===")
    log_progress(processed_batches, total_batches, "批次进度", f"当前: 批次{batch_num}", batch_start_time)
    
    # 检查是否已有翻译结果
    batch_id = f"batch_{batch_num:03d}"
    batch_md_file = CHAP_DIR / f"{batch_id}.md"
    if batch_md_file.exists():
        try:
            cached_content = batch_md_file.read_text(encoding="utf-8")
            if cached_content.strip():
                logging.info(f"💾 批次 {batch_num} 已存在翻译结果，跳过处理")
                big_md_parts.append(cached_content)
                log_progress(processed_batches, total_batches, "批次进度", "使用缓存", batch_start_time)
                continue
        except Exception as e:
            logging.warning(f"读取批次翻译缓存失败: {e}，重新处理")
    
    try:
        # 获取批次原始英文文本
        raw_eng = get_batch_text_with_cache(pages, batch_num, p_start, p_end, RAW_CONTENT_DIR)
        
        if not raw_eng.strip():
            logging.warning(f"📄 批次{batch_num}内容为空，跳过")
            MISSING_DICT[batch_id] = ["整批缺失"]
            log_progress(processed_batches, total_batches, "批次进度", "内容为空", batch_start_time)
            continue
        
        # 句子完整性处理
        if batch_num < total_batches:  # 不是最后一个批次
            try:
                next_p_start = batch_num * PAGES_PER_BATCH + 1
                next_p_end = min((batch_num + 1) * PAGES_PER_BATCH, total_pages)
                
                next_batch_text = get_batch_text_with_cache(pages, batch_num + 1, next_p_start, next_p_end, RAW_CONTENT_DIR)
                # 只传递下一批次的前1000字符用于句子完整性检查
                next_batch_preview = next_batch_text[:1000] if next_batch_text else ""
                
                raw_eng = ensure_sentence_completion(raw_eng, next_batch_preview)
            except Exception as e:
                logging.warning(f"获取下一批次文本失败，跳过句子完整性处理: {e}")
                # 如果获取下一批次失败，仍然进行基本的句子完整性处理
                raw_eng = ensure_sentence_completion(raw_eng)
        
        # 添加段落标签
        tagged_eng = wrap_batch_with_tags(raw_eng)
        
        # 检查分段结果
        tag_count = len(re.findall(r'<c\d+>', tagged_eng))
        if tag_count == 0:
            logging.warning(f"⚠️  批次{batch_num}未能正确分段")
        else:
            logging.info(f"📝 批次{batch_num}分为{tag_count}个段落，文本长度: {len(raw_eng)} 字符")
        
        # 风格分析（仅第一次）
        if not style_cache:
            logging.info("📝 开始文本风格分析...")
            text_length = len(raw_eng)
            sample_length = min(5000, text_length)  # 样本长度不超过文本总长度
            
            if text_length > sample_length:
                # 从文本中间随机取样，避免开头可能的目录或结尾的版权信息
                start_range_begin = int(text_length * 0.2)
                start_range_end = int(text_length * 0.8) - sample_length
                
                if start_range_end > start_range_begin:
                    start_pos = random.randint(start_range_begin, start_range_end)
                    sample_text = raw_eng[start_pos:start_pos + sample_length]
                    logging.info(f"📝 从文本中间随机取样进行风格分析 (位置: {start_pos}-{start_pos + sample_length})")
                else:
                    # 如果范围太小，从中间取样
                    start_pos = max(0, (text_length - sample_length) // 2)
                    sample_text = raw_eng[start_pos:start_pos + sample_length]
                    logging.info(f"📝 从文本中间取样进行风格分析 (位置: {start_pos}-{start_pos + sample_length})")
            else:
                # 文本较短，使用全部内容
                sample_text = raw_eng
                logging.info("📝 文本较短，使用全部内容进行风格分析")
            
            refresh_style(sample_text)
        
        # 构建系统提示
        system_prompt = textwrap.dedent( f"""
            你是资深文学译者，将下方小说精准优雅地译成现代中文。
            
            ===== 核心要求 =====
            1. **段落对齐**：每个<cN>段落必须对应输出<cN>段落，不可合并/跳过。无法翻译时用<cN>{{{{MISSING}}}}</cN>。
            2. **完整性**：必须翻译所有段落，特别注意最后一段！完成后检查是否有遗漏。
            3. **专有名词处理**（严格遵守）：
               • 人名：保持英文原文不翻译（如：John, Mary, Smith等）
               • 泰语称呼：保持原文（如：Khun, P', N', Phi, Nong, Ajarn, Krub, Ka等）
            4. **页眉页脚处理**：
               • 页码 → <cN>[页眉页脚]</cN>
               • 重复的作者署名 → <cN>[页眉页脚]</cN>
               • 其他与正文无关的元数据 → <cN>[页眉页脚]</cN>
            5. **特殊标记**：
               • 章节标题 → ## 第XX章 标题（严格两位数编号：01、02、03...，去除所有装饰符号）
               • 序章/尾声/作者话 → ## 序章 / ## 尾声 / ## 作者的话
               • 番外/特别篇/外传 → ## 番外01 标题内容 / ## 特别篇01 标题内容 / ## 外传01 标题内容
               • 作者的话、前言、后记等 → ## 作者的话
               • 目录、索引等 → [目录]
               • 分隔符 → ——————————（统一使用6个长横线）
            6. **文学性**：追求韵律美感，准确传达情感，保留修辞手法，营造意境，适应中文表达习惯。
            7. **风格**：保持原文特征{style_cache}，第三人称对话改第一人称，中文标点，连续句号改省略号，优选文学词汇。
            
            ===== 重要提醒 =====
            • 必须将所有段落翻译成中文，输出<cN>标签数量与输入完全对应
            • 无法翻译时使用<cN>{{{{MISSING}}}}</cN>
            • 如果遇到无法理解的内容，使用<cN>{{{{MISSING}}}}</cN>而不是跳过
            • 绝对不能跳过任何段落，即使内容很短或看似不重要
            • 专有名词（人名、地名、品牌名、机构名、泰语称呼）必须保持原文不翻译
            
            ===== 输出格式 =====
            <c1>第一段译文</c1>
            <c2>第二段译文</c2>
            ...
            <cN>最后一段译文</cN>
            """).strip()
        
        # 调用豆包API进行翻译
        logging.info(f"🤖 开始翻译批次 {batch_num}...")
        translated_content = call_llm(system_prompt, tagged_eng)
        
        if not translated_content or not translated_content.strip():
            logging.error(f"❌ 批次{batch_num}翻译结果为空")
            MISSING_DICT[batch_id] = ["翻译结果为空"]
            continue
        
        # 验证翻译结果
        input_tags = len(re.findall(r'<c\d+>', tagged_eng))
        output_tags = len(re.findall(r'<c\d+>', translated_content))
        
        if input_tags != output_tags:
            warning_msg = f"段落数量不匹配: 输入{input_tags}个，输出{output_tags}个"
            logging.warning(f"⚠️  批次{batch_num} {warning_msg}")
            WARNING_DICT[batch_id] = warning_msg
        
        # 保存翻译结果
        try:
            batch_md_file.write_text(translated_content, encoding="utf-8")
            logging.info(f"💾 批次{batch_num}翻译结果已保存: {batch_md_file.name}")
        except Exception as e:
            logging.error(f"❌ 保存批次{batch_num}翻译结果失败: {e}")
            continue
        
        # 添加到最终结果
        big_md_parts.append(translated_content)
        
        logging.info(f"✅ 批次{batch_num}处理完成")
        log_progress(processed_batches, total_batches, "批次进度", "翻译完成", batch_start_time)
        
    except Exception as e:
        logging.error(f"❌ 批次{batch_num}处理失败: {e}")
        MISSING_DICT[batch_id] = [f"处理失败: {e}"]
        continue

# ========= 最终整合和统计 ========= #

logging.info("=== 开始最终整合 ===")

# 合并所有翻译结果
if big_md_parts:
    final_content = "\n\n".join(big_md_parts)
    
    # 添加文档头部信息
    header = textwrap.dedent(f"""
        # 翻译文档
        
        **翻译时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        **源文件**: {PDF_PATH.name}
        **模型**: doubao-seed-1-6
        **总页数**: {total_pages}
        **总批次**: {total_batches}
        
        ---
        
        """)
    
    final_content = header + final_content
    
    # 保存最终文档
    final_md_path = OUT_DIR / BIG_MD_NAME
    try:
        final_md_path.write_text(final_content, encoding="utf-8")
        logging.info(f"📄 最终翻译文档已保存: {final_md_path}")
    except Exception as e:
        logging.error(f"❌ 保存最终文档失败: {e}")
else:
    logging.error("❌ 没有任何翻译内容可以整合")

# 统计信息
logging.info("=== 翻译统计 ===")
logging.info(f"📊 总页数: {total_pages}")
logging.info(f"📊 总批次: {total_batches}")
logging.info(f"📊 成功批次: {len(big_md_parts)}")
logging.info(f"📊 失败批次: {len(MISSING_DICT)}")
logging.info(f"📊 警告批次: {len(WARNING_DICT)}")

# Token和成本统计
if total_input_tokens > 0 or total_output_tokens > 0:
    logging.info(f"📊 总输入Token: {total_input_tokens:,}")
    logging.info(f"📊 总输出Token: {total_output_tokens:,}")
    logging.info(f"📊 总Token: {total_input_tokens + total_output_tokens:,}")
    
    if CONFIG.get('pricing', {}).get('enable_cost_tracking', False):
        currency = CONFIG.get('pricing', {}).get('currency', 'USD')
        logging.info(f"💰 总成本: {total_cost:.4f} {currency}")

# 失败和警告详情
if MISSING_DICT:
    logging.warning("⚠️  失败批次详情:")
    for batch_id, errors in MISSING_DICT.items():
        logging.warning(f"   {batch_id}: {', '.join(errors)}")

if WARNING_DICT:
    logging.warning("⚠️  警告批次详情:")
    for batch_id, warning in WARNING_DICT.items():
        logging.warning(f"   {batch_id}: {warning}")

# 生成重试脚本
if MISSING_DICT:
    retry_script_path = OUT_DIR / "retry_failed_batches.py"
    retry_script_content = textwrap.dedent(f"""
        #!/usr/bin/env python3
        # -*- coding: utf-8 -*-
        '''
        重试失败批次的翻译脚本
        自动生成于: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        '''
        
        import os
        import sys
        from pathlib import Path
        
        # 失败的批次列表
        failed_batches = {list(MISSING_DICT.keys())}
        
        print(f"检测到 {{len(failed_batches)}} 个失败批次:")
        for batch in failed_batches:
            print(f"  - {{batch}}")
        
        print("\n要重试这些批次，请:")
        print("1. 检查网络连接和API配置")
        print("2. 删除对应的缓存文件（如果需要）")
        print("3. 重新运行主翻译脚本")
        
        # 可以在这里添加自动重试逻辑
        """)
    
    try:
        retry_script_path.write_text(retry_script_content, encoding="utf-8")
        logging.info(f"📝 重试脚本已生成: {retry_script_path}")
    except Exception as e:
        logging.warning(f"⚠️  生成重试脚本失败: {e}")

# 计算总耗时
total_time = time.time() - batch_start_time
logging.info(f"⏱️  总耗时: {total_time/60:.1f} 分钟")

logging.info("=== 豆包PDF翻译完成 ===")

if len(big_md_parts) == total_batches:
    logging.info("🎉 所有批次翻译成功！")
else:
    logging.warning(f"⚠️  部分批次翻译失败，成功率: {len(big_md_parts)/total_batches*100:.1f}%")

logging.info(f"📄 翻译结果保存在: {OUT_DIR}")
logging.info(f"📄 最终文档: {OUT_DIR / BIG_MD_NAME}")