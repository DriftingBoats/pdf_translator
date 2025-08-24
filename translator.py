#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
page_batch_translation_agent_cn.py
—— 按页数分批 PDF 英译本 → 中文译本批量翻译脚本
  • 按指定页数X自动分批翻译
  • 处理句子完整性，确保翻译至句子结束
  • 自动识别标题并保持格式
  • 自动编号并最终整合为一个文件
  • 使用prompt约束专有名词处理
"""
import json, re, textwrap, logging, time, datetime, requests, os, sys, warnings, random
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 过滤PyMuPDF的警告信息
warnings.filterwarnings("ignore", category=UserWarning, module="fitz")

import fitz  # PyMuPDF - pip install PyMuPDF

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
                raise KeyError(f"配置文件缺少必需项: {key}")
        
        # 验证API配置
        api_keys = ["API_URL", "API_KEY", "LLM_MODEL"]
        for key in api_keys:
            if key not in config["api"]:
                raise KeyError(f"API配置缺少必需项: {key}")
        
        # 验证路径配置
        path_keys = ["pdf", "output_dir", "big_md_name"]
        for key in path_keys:
            if key not in config["paths"]:
                raise KeyError(f"路径配置缺少必需项: {key}")
        
        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件JSON格式错误: {e}")
    except Exception as e:
        raise RuntimeError(f"加载配置文件失败: {e}")

ROOT = Path(__file__).resolve().parent

# 交互式获取配置文件路径
def get_config_path() -> str:
    """交互式获取配置文件路径"""
    if len(sys.argv) > 1:
        return sys.argv[1]
    
    print("请选择配置文件:")
    print("1. 使用默认配置 (config.json)")
    print("2. 输入自定义配置文件路径")
    
    while True:
        choice = input("请输入选择 (1/2): ").strip()
        if choice == "1":
            return "config.json"
        elif choice == "2":
            config_path = input("请输入配置文件路径: ").strip()
            if config_path:
                return config_path
            else:
                print("路径不能为空，请重新输入")
        else:
            print("无效选择，请输入 1 或 2")

config_file = get_config_path()
CONFIG: Dict = load_config(config_file)
print(f"使用配置文件: {config_file}")

API_URL      = CONFIG["api"]["API_URL"]
API_KEY      = CONFIG["api"]["API_KEY"]
LLM_MODEL    = CONFIG["api"]["LLM_MODEL"]
TEMPERATURE  = CONFIG["api"].get("temperature", 0.2)

PDF_PATH     = Path(CONFIG["paths"]["pdf"])
OUT_DIR      = Path(CONFIG["paths"]["output_dir"])
BIG_MD_NAME  = CONFIG["paths"]["big_md_name"]

# 新增配置项：每批处理的页数
PAGES_PER_BATCH = CONFIG.get("pages_per_batch", 10)  # 默认每10页翻译一次

# 验证PDF文件存在
if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF文件不存在: {PDF_PATH}")

# ========= 缓存管理 ========= #

# 初始化style_cache相关
STYLE_FILE = OUT_DIR / "style_cache.txt"
style_cache = ""
if STYLE_FILE.exists():
    try:
        style_cache = STYLE_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:
        logging.warning(f"读取风格缓存失败: {e}")
        style_cache = ""

# ========= 常量 ========= #
HEAD_SEP  = "\n" + ("─"*80) + "\n"
TAG_PAT   = re.compile(r"<c\d+>(.*?)</c\d+>", re.S)
# NEWTERM_PAT已移除，不再处理术语表

# ========= 日志配置 ========= #
class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record):
        # 添加颜色
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # 格式化时间
        record.asctime = self.formatTime(record, self.datefmt)
        
        # 根据日志级别使用不同格式
        if record.levelname == 'INFO':
            if '===' in record.getMessage():
                # 批次处理标题
                return f"{color}{'='*60}{reset}\n{color}[{record.asctime}] {record.getMessage()}{reset}\n{color}{'='*60}{reset}"
            elif '进度:' in record.getMessage():
                # 进度信息
                return f"{color}[{record.asctime}] 📊 {record.getMessage()}{reset}"
            elif '缓存' in record.getMessage():
                # 缓存相关
                return f"{color}[{record.asctime}] 💾 {record.getMessage()}{reset}"
            elif '完成' in record.getMessage() or '成功' in record.getMessage():
                # 成功信息
                return f"{color}[{record.asctime}] ✅ {record.getMessage()}{reset}"
            else:
                return f"{color}[{record.asctime}] ℹ️  {record.getMessage()}{reset}"
        elif record.levelname == 'WARNING':
            return f"{color}[{record.asctime}] ⚠️  {record.getMessage()}{reset}"
        elif record.levelname == 'ERROR':
            return f"{color}[{record.asctime}] ❌ {record.getMessage()}{reset}"
        else:
            return f"{color}[{record.asctime}] [{record.levelname}] {record.getMessage()}{reset}"

def setup_logging(verbose: bool = False):
    """设置日志系统"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # 清除现有的处理器
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter(datefmt="%H:%M:%S"))
    
    # 配置根日志器
    logging.basicConfig(
        level=level,
        handlers=[console_handler],
        force=True
    )

def log_progress(current: int, total: int, prefix: str = "进度", suffix: str = ""):
    """显示进度条"""
    percent = (current / total) * 100
    bar_length = 30
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    logging.info(f"{prefix}: [{bar}] {percent:.1f}% ({current}/{total}) {suffix}")

# 初始化日志系统
setup_logging(verbose=CONFIG.get('verbose_logging', False))

# ========= 辅助函数 ========= #
# 移除了detect_titles函数，现在由LLM负责识别标题和页眉页码

def ensure_sentence_completion(text: str, next_batch_text: str = "") -> str:
    """智能句子完整性处理：如果当前batch最后一句没有结束，只补充完整这个半句"""
    if not text.strip():
        return text
    
    # 移除末尾空白字符
    text = text.rstrip()
    
    # 如果没有下一批次内容，直接返回
    if not next_batch_text.strip():
        return text
    
    # 检查最后一句是否完整（以句号、问号、感叹号、引号等结束）
    sentence_endings = r'[.!?"\'\'\"\)\]\}]\s*$'
    
    # 如果最后一句已经完整，直接返回
    if re.search(sentence_endings, text):
        return text
    
    # 如果最后一句没有完整，从下一批次中找到句子结束位置
    next_text = next_batch_text.strip()
    
    # 优先根据空行（段落边界）查找句子结束位置
    # 首先查找第一个空行（双换行符），这通常表示段落结束
    paragraph_end_match = re.search(r'\n\s*\n', next_text)
    
    if paragraph_end_match:
        # 找到段落结束位置，补充到段落结束
        end_pos = paragraph_end_match.start()
        completion = next_text[:end_pos].rstrip()
        
        # 记录补充的内容长度，用于日志
        logging.info(f"📝 检测到未完整句子，根据段落边界补充 {len(completion)} 个字符完成句子")
        
        return text + completion
    else:
        # 如果没有找到段落边界，再查找标点符号结束位置
        sentence_end_match = re.search(r'[.!?"\'\'\"\)\]\}]', next_text)
        
        if sentence_end_match:
            # 找到句子结束位置，只补充到句子结束
            end_pos = sentence_end_match.end()
            completion = next_text[:end_pos]
            
            # 记录补充的内容长度，用于日志
            logging.info(f"📝 检测到未完整句子，根据标点符号补充 {len(completion)} 个字符完成句子")
            
            return text + completion
        else:
            # 如果都没有找到，只补充一小部分内容（最多100字符）
            max_supplement = min(100, len(next_text))
            completion = next_text[:max_supplement]
            
            logging.info(f"📝 未找到明确句子结束，补充 {len(completion)} 个字符")
            
            return text + completion

def wrap_batch_with_tags(raw_text: str) -> str:
    """把批次原文按空行分段，加 <c1>…</c1> 标签，让LLM自行识别标题和页眉页码"""
    segments = [seg.strip() for seg in re.split(r"\n\s*\n", raw_text) if seg.strip()]
    tagged = []
    
    for idx, seg in enumerate(segments, start=1):
        # 不再预先标记标题，让LLM自行识别和处理
        tagged.append(f"<c{idx}>{seg}</c{idx}>")
    
    return "\n\n".join(tagged)

def strip_tags(llm_output: str, keep_missing: bool = True):
    """清洗 LLM 输出 & 收集缺失段，优化页眉页脚识别逻辑"""
    paragraphs = TAG_PAT.findall(llm_output)

    miss_list, clean_paras = [], []
    for idx, p in enumerate(paragraphs, start=1):
        content = p.strip()
        
        if content == "{{MISSING}}":
            miss_list.append(f"c{idx:03d}")
            if keep_missing:
                clean_paras.append("{{MISSING}}")
        elif content == "":
            # 跳过完全空的内容
            pass
        elif _is_header_footer_content(content):
            # 使用更智能的页眉页脚识别逻辑
            pass
        else:
            clean_paras.append(content)

    # 过滤掉空字符串，避免多余的空行
    clean_paras = [para for para in clean_paras if para.strip()]
    pure_text = "\n\n".join(clean_paras)
    # 术语表功能已移除，不再处理术语表内容
    return pure_text, "", miss_list

def _is_header_footer_content(content: str) -> bool:
    """智能识别页眉页脚内容，避免误判正常文本"""
    # 明确的页眉页脚标记
    if content.startswith("[页眉页脚]") or content.startswith("[目录]"):
        return True
    
    # 页码模式（更严格的匹配）
    page_patterns = [
        r'^Page\s+\d+\s+of\s+\d+$',  # "Page 1 of 506"
        r'^第\d+页/共\d+页$',        # "第1页/共506页"
        r'^\d+\s*/\s*\d+$',         # "1/506"
        r'^\d+$'                    # 单独的数字（但要小心，可能是正文）
    ]
    
    for pattern in page_patterns:
        if re.match(pattern, content.strip(), re.IGNORECASE):
            return True
    
    # 网址和邮箱模式
    if re.search(r'https?://|www\.|@.*\.(com|org|net)', content, re.IGNORECASE):
        return True
    
    # 版权信息
    if re.search(r'copyright|©|版权所有|all rights reserved', content, re.IGNORECASE):
        return True
    
    # 作者信息重复（但要谨慎，避免误判正文中的作者名）
    # 只有当内容很短且看起来像重复的作者信息时才判断为页眉页脚
    if len(content) < 50 and re.search(r'^(author|作者)[:：]?\s*[A-Za-z\s]+$', content, re.IGNORECASE):
        return True
    
    return False

def refresh_style(sample_text: str):
    """若 style_cache 为空，则用原文样本让 LLM 归纳风格；否则跳过"""
    global style_cache
    if style_cache:
        return
    
    try:
        prompt_sys = "You are a literary critic. Analyze the writing style concisely."
        # 确保样本文本不超过2000字符，避免API限制
        sample_text = sample_text[:2000] if len(sample_text) > 2000 else sample_text
        prompt_user = f"""Summarize the narrative voice, tone, humor level and sentence rhythm of the following English text in 80 words:

{sample_text}"""
        
        style_cache = call_llm(prompt_sys, prompt_user)
        if style_cache:
            STYLE_FILE.write_text(style_cache, encoding="utf-8")
            logging.info("风格分析完成并已缓存")
        else:
            raise ValueError("风格分析返回空结果")
    except Exception as e:
        logging.error(f"风格分析失败: {e}")
        style_cache = "默认风格：保持原文的叙事节奏和语调"

# 术语表相关函数已移除，不再使用术语表功能

def call_llm(prompt_sys: str, prompt_user: str, max_retries: int = 3, timeout: int = 120) -> str:
    """调用LLM API，带重试和错误处理"""
    global total_cost, total_input_tokens, total_output_tokens
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": prompt_sys},
            {"role": "user", "content": prompt_user}
        ]
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logging.info(f"🤖 调用LLM API - 模型: {LLM_MODEL} (尝试 {attempt+1}/{max_retries})")
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
            
            logging.info(f"✅ LLM响应成功 - 输出长度: {len(content)} 字符")
            
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
            logging.warning(f"LLM调用超时({attempt+1}/{max_retries})")
        except requests.exceptions.ConnectionError:
            last_error = "网络连接错误"
            logging.warning(f"LLM调用网络错误({attempt+1}/{max_retries})")
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP错误: {e.response.status_code}"
            logging.warning(f"LLM调用HTTP错误({attempt+1}/{max_retries}): {e}")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            last_error = f"响应解析错误: {e}"
            logging.warning(f"LLM调用解析错误({attempt+1}/{max_retries}): {e}")
        except Exception as e:
            last_error = f"未知错误: {e}"
            logging.warning(f"LLM调用未知错误({attempt+1}/{max_retries}): {e}")
        
        if attempt < max_retries - 1:
            wait_time = min(5 * (2 ** attempt), 30)  # 指数退避，最大30秒
            logging.info(f"等待{wait_time}秒后重试...")
            time.sleep(wait_time)
    
    raise RuntimeError(f"LLM调用失败，已重试{max_retries}次。最后错误: {last_error}")

# ========= 准备输出目录 ========= #
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

# 检查是否需要清理过期缓存
if CONFIG.get("clean_cache_on_start", True):
    logging.info("=== 检查并清理过期缓存文件 ===")
    clean_cache_files(RAW_CONTENT_DIR, PDF_PATH, force=False)

# 术语表功能已移除，不再使用术语表
logging.info("术语表功能已禁用，使用prompt约束专有名词处理")

# ========= 解析整本 PDF（带缓存优化）========= #
def get_pdf_text_with_cache(pdf_path: Path, cache_dir: Path) -> str:
    """获取PDF文本，优先使用缓存"""
    # 生成缓存文件路径
    pdf_name = pdf_path.stem
    cache_file = cache_dir / f"{pdf_name}_text_cache.txt"
    
    # 检查缓存是否存在且有效
    if cache_file.exists():
        try:
            pdf_mtime = pdf_path.stat().st_mtime
            cache_mtime = cache_file.stat().st_mtime
            
            # 如果缓存文件比PDF文件新，使用缓存
            if cache_mtime >= pdf_mtime:
                cache_size = cache_file.stat().st_size
                logging.info(f"💾 使用PDF文本缓存: {cache_file.name} ({cache_size/1024:.1f}KB)")
                cached_text = cache_file.read_text(encoding="utf-8")
                logging.info(f"📄 缓存文本长度: {len(cached_text)} 字符")
                return cached_text
            else:
                logging.info("📝 PDF文件已更新，重新提取文本")
        except Exception as e:
            logging.warning(f"读取缓存失败: {e}，将重新提取PDF文本")
    
    # 提取PDF文本
    logging.info(f"🔍 开始提取PDF文本: {pdf_path.name}")
    import time
    start_time = time.time()
    
    # 使用PyMuPDF提取文本，更好地处理段落结构
    doc = fitz.open(str(pdf_path))
    pages = []
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        # 使用sort=True获得更好的阅读顺序
        # 使用blocks模式获得更好的段落结构
        blocks = page.get_text("blocks", sort=True)
        page_text = ""
        
        for block in blocks:
            if len(block) >= 5 and block[4]:  # 文本块
                block_text = block[4].strip()
                if block_text:
                    page_text += block_text + "\n\n"
        
        pages.append(page_text.rstrip())
    
    doc.close()
    full_text = "\f".join(pages)  # 保持与原来的分页符一致
    
    extract_time = time.time() - start_time
    
    # 保存到缓存
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(full_text, encoding="utf-8")
        cache_size = cache_file.stat().st_size
        logging.info(f"💾 PDF文本已缓存: {cache_file.name} ({cache_size/1024:.1f}KB, 耗时{extract_time:.1f}秒)")
        logging.info(f"📄 提取文本长度: {len(full_text)} 字符")
    except Exception as e:
        logging.warning(f"保存文本缓存失败: {e}")
    
    return full_text

logging.info(f"开始加载PDF文件: {PDF_PATH}")
try:
    # 获取PDF文本（使用缓存）
    full_text = get_pdf_text_with_cache(PDF_PATH, RAW_CONTENT_DIR)
    if not full_text or not full_text.strip():
        raise ValueError("PDF文件内容为空或无法提取文本")
    
    pages = re.split(r"\f", full_text)                           # PyMuPDF 按 formfeed 分页
    if pages and pages[-1] == "":
        pages.pop()
    
    logging.info(f"PDF加载完成，共{len(pages)}页")
    
    # 验证页数配置
    max_page = len(pages)
    if PAGES_PER_BATCH < 1:
        raise ValueError(f"每批页数必须大于0，当前设置: {PAGES_PER_BATCH}")
    
    logging.info(f"将按每{PAGES_PER_BATCH}页进行分批翻译，PDF共{max_page}页")
    
except Exception as e:
    raise RuntimeError(f"PDF处理失败: {e}")

# ========= 汇总输出 ========= #
MISSING_DICT = {}
WARNING_DICT = {}  # 收集段落数量差异等警告信息
big_md_parts = []
total_pages = len(pages)
total_batches = (total_pages + PAGES_PER_BATCH - 1) // PAGES_PER_BATCH  # 向上取整
processed_batches = 0

logging.info(f"=== 开始分批翻译处理 ===")
logging.info(f"总批次: {total_batches} | 每批页数: {PAGES_PER_BATCH} | 总页数: {total_pages}")

def get_batch_text_with_cache(pages: List[str], batch_num: int, p_start: int, p_end: int, cache_dir: Path) -> str:
    """获取批次文本，优先使用缓存"""
    batch_id = f"batch_{batch_num:03d}"
    cache_file = cache_dir / f"{batch_id}_raw_text.txt"
    
    # 检查批次文本缓存
    if cache_file.exists():
        try:
            cached_text = cache_file.read_text(encoding="utf-8")
            if cached_text.strip():
                cache_size = cache_file.stat().st_size
                logging.debug(f"💾 使用批次文本缓存: {cache_file.name} ({cache_size/1024:.1f}KB)")
                logging.debug(f"📄 批次文本长度: {len(cached_text)} 字符")
                return cached_text
        except Exception as e:
            logging.warning(f"读取批次缓存失败: {e}")
    
    # 从pages数组中提取文本
    raw_eng = "\n".join(pages[p_start-1:p_end])  # 页码从 1 开始
    
    # 保存批次文本缓存
    try:
        cache_file.write_text(raw_eng, encoding="utf-8")
        cache_size = cache_file.stat().st_size
        logging.debug(f"💾 批次文本已缓存: {cache_file.name} ({cache_size/1024:.1f}KB)")
        logging.debug(f"📄 批次文本长度: {len(raw_eng)} 字符")
    except Exception as e:
        logging.warning(f"保存批次缓存失败: {e}")
    
    return raw_eng

# 按页数分批处理
for batch_num in range(1, total_batches + 1):
    processed_batches += 1
    
    # 计算当前批次的页码范围
    p_start = (batch_num - 1) * PAGES_PER_BATCH + 1
    p_end = min(batch_num * PAGES_PER_BATCH, total_pages)
    batch_id = f"batch_{batch_num:03d}"
    
    logging.info(f"=== 处理批次 {batch_num}/{total_batches} (页 {p_start}-{p_end}) ===")
    log_progress(processed_batches, total_batches, "批次进度", f"当前: 批次{batch_num}")
    
    # 检查是否已有翻译结果缓存
    batch_md_file = CHAP_DIR / f"{batch_id}.md"
    if batch_md_file.exists():
        try:
            cached_content = batch_md_file.read_text(encoding="utf-8")
            if cached_content.strip():
                logging.info(f"💾 批次 {batch_num} 已存在翻译结果，跳过处理")
                big_md_parts.append(cached_content)
                log_progress(processed_batches, total_batches, "批次进度", "使用缓存")
                continue
        except Exception as e:
            logging.warning(f"读取批次翻译缓存失败: {e}，重新处理")
    
    try:
        # 获取批次文本（使用缓存）
        raw_eng = get_batch_text_with_cache(pages, batch_num, p_start, p_end, RAW_CONTENT_DIR)
        
        if not raw_eng.strip():
            logging.warning(f"📄 批次{batch_num}内容为空，跳过")
            MISSING_DICT[batch_id] = ["整批缺失"]
            log_progress(processed_batches, total_batches, "批次进度", "内容为空")
            continue
        
        # 智能句子完整性处理：如果当前批次最后一句没有结束，从下一批次补充完整
        if batch_num < total_batches:  # 不是最后一个批次
            # 获取下一批次的文本用于句子完整性检查
            next_p_start = batch_num * PAGES_PER_BATCH + 1
            next_p_end = min((batch_num + 1) * PAGES_PER_BATCH, total_pages)
            try:
                next_batch_text = get_batch_text_with_cache(pages, batch_num + 1, next_p_start, next_p_end, RAW_CONTENT_DIR)
                # 应用智能句子完整性处理
                raw_eng = ensure_sentence_completion(raw_eng, next_batch_text)
            except Exception as e:
                logging.warning(f"获取下一批次文本失败，跳过句子完整性处理: {e}")
                # 如果获取下一批次失败，仍然使用原始文本
                raw_eng = ensure_sentence_completion(raw_eng)
        
        tagged_eng = wrap_batch_with_tags(raw_eng)
        
        # 检查标签数量是否合理
        tag_count = len(re.findall(r'<c\d+>', tagged_eng))
        if tag_count == 0:
            logging.warning(f"⚠️  批次{batch_num}未能正确分段")
        else:
            logging.info(f"📝 批次{batch_num}分为{tag_count}个段落，文本长度: {len(raw_eng)} 字符")

        # --- 获取风格信息 ---
        if not style_cache:
            # 从中间随机取样作为风格分析样本，避免取到前言、作者的话等内容
            text_length = len(raw_eng)
            sample_length = min(5000, text_length)  # 样本长度不超过文本总长度
            
            if text_length > sample_length:
                # 从文本的中间部分随机选择起始位置
                # 避免前20%和后20%的内容，主要从中间60%的部分取样
                start_range_begin = int(text_length * 0.2)
                start_range_end = int(text_length * 0.8) - sample_length
                
                if start_range_end > start_range_begin:
                    start_pos = random.randint(start_range_begin, start_range_end)
                    sample_text = raw_eng[start_pos:start_pos + sample_length]
                    logging.info(f"📝 从文本中间随机取样进行风格分析 (位置: {start_pos}-{start_pos + sample_length})")
                else:
                    # 如果文本太短，就取中间部分
                    start_pos = max(0, (text_length - sample_length) // 2)
                    sample_text = raw_eng[start_pos:start_pos + sample_length]
                    logging.info(f"📝 从文本中间取样进行风格分析 (位置: {start_pos}-{start_pos + sample_length})")
            else:
                # 文本长度不足5000字符，直接使用全部文本
                sample_text = raw_eng
                logging.info("📝 文本较短，使用全部内容进行风格分析")
            
            refresh_style(sample_text)
        
        # --- 构造系统提示 ---
        system_prompt = textwrap.dedent( f"""
            你是一名资深文学译者，精通中英文学创作，需把下方小说精准、优雅地译成现代中文，追求文学性与可读性的完美平衡。

            ================ 任务要求 ================
            1. **逐段落对齐**  
            • 源英文用 <cN>…</cN> 标签包裹（脚本已自动加）。  
            • 你必须为 *每一个* <cN> 段落输出对应 <cN> 段落，保持顺序一致。  
            • 绝不可合并、增删或跳过段落。若确实无法翻译，原文用 <cN>{{{{MISSING}}}}</cN> 原样抄写。

            2. **不省略**（极其重要！）  
            • 译文行数 ≈ 源行数。  
            • **必须翻译每一个段落**：特别注意最后一个段落，绝不能遗漏！ 
            • **强制完整性检查**：翻译完成后，必须检查是否所有 <cN> 段落都有对应输出。 
            • 结尾自行执行检查：若发现有未输出的 <cX> 段，必须补上 <cX>{{{{MISSING}}}}</cX>。 
            • **最后一段特别提醒**：最后一个段落往往容易被遗漏，请务必确保翻译完整！

            3. **智能识别与处理**（重要！） 
            • **页眉页脚标记**：遇到以下内容输出特殊标记 <cN>[页眉页脚]</cN>： 
              - 页码信息（如"Page 1 of 506"、"第1页/共506页"等） 
              - 作者信息重复（如邮箱地址、作者名重复出现） 
              - 网站链接、版权信息 
              - 明显的页眉页脚重复内容 
            • **章节标题识别与格式统一**：识别以下内容并转换为统一的Markdown格式（二级标题##）： 
               - **正文章节**："Chapter X"、"第X章"、"第01章"、"第一章" → ## 第X章 
               - **编号章节**："01."、"1."、"一、"、"Chapter 1:"等编号开头的标题 → ## 第01章 标题内容 
               - **特殊章节**："番外01."、"特别篇01."、"外传01." → ## 番外01 标题内容、## 特别篇01 标题内容 
               - **序章结尾**："PROLOGUE"、"序章"、"楔子" → ## 序章、"EPILOGUE"、"尾声"、"后记" → ## 尾声 
               - **装饰标题**：带有装饰性符号的标题（如"☘ 01.我忍不了了 ☘"、"★第一章★"）→ 去掉装饰符号后转换为 ## 第01章 我忍不了了 
               - **居中短标题**：明显的章节标题（通常独立成行、字数较少）→ ## 标题内容 
               - **格式要求**：章节编号统一为两位数字（如第01章、第02章），标题与编号之间用空格分隔 
            • **特殊内容处理**： 
              - 作者的话、前言、后记等 → ## 作者的话
              - 目录、索引等 → [目录]

            4. **专有名词和称呼处理**（重要！）  
            • **人名保持原文**：所有人名（如 John、Mary、Somchai 等）保持英文原文，不要翻译成中文。 
            • **泰语称呼保持原文**：以下泰语称呼词汇必须保持原文，不要翻译： 
              - Khun（คุณ）- 敬语称呼，相当于先生/女士 
              - P'（พี่）- 对年长者的称呼，哥哥/姐姐 
              - N'（น้อง）- 对年幼者的称呼，弟弟/妹妹 
              - Phi（พี่）- P'的完整形式 
              - Nong（น้อง）- N'的完整形式 
              - Ajarn（อาจารย์）- 老师、教授 
              - Krub/Krab（ครับ）- 男性敬语语尾词 
              - Ka/Kha（ค่ะ/คะ）- 女性敬语语尾词 
            • **品牌名保持原文**：品牌名称保持原文不翻译。

            5. **文学性翻译要求**（核心！）
            • **语言美感**：追求译文的韵律感和节奏感，避免生硬直译，注重语言的流畅性和优美性。
            • **情感传达**：深度理解原文的情感色彩，准确传达人物的内心世界、情绪变化和心理状态。
            • **修辞保留**：保留并转化原文的修辞手法，如比喻、拟人、排比等，使其符合中文表达习惯。
            • **意境营造**：注重营造文学意境，通过词汇选择和句式安排，创造富有诗意的阅读体验。
            • **文化转换**：将英文的文化背景和表达方式巧妙转换为中文读者能够理解和共鸣的形式。
            • **层次丰富**：根据不同场景选择合适的语言风格，如抒情段落用词优美，对话部分生动自然，描写段落细腻入微。

            6. **风格守则**  
            • 保持原文风格特征：{style_cache} 
            • **第三人称改第一人称**：泰语转译中常见用第三人称称呼自己的对话，必须改成第一人称以符合中文阅读习惯。 
            • **标点规范**：用中文标点，英文专名内部保留半角。禁止出现多个连续句号（如。。。、.。。。、.。.等），统一使用省略号……。  
            • **词汇选择**：优先选择富有文学色彩的词汇，避免过于口语化或生硬的表达，追求雅俗共赏的语言风格。
            • **句式变化**：灵活运用长短句结合，避免句式单调，营造丰富的语言节奏。
            • 数字、计量单位、货币符号照原文。 
            • 保持原文的叙事节奏、语调和情感表达方式，同时提升中文表达的文学性。

            ===== 输出格式示例 ===== 
            输入： 
            <c1>Page 1 of 506</c1> 
            <c2>Khun Somchai said to P'Niran</c2> 
            <c3>Chapter 1: The Beginning</c3> 
            <c4>☘ 02.Love Story ☘</c4>
            <c5>"I love you," John whispered to Mary.</c5>

            输出： 
            <c1>[页眉页脚]</c1> 
            <c2>Khun Somchai对P'Niran说</c2> 
            <c3>## 第01章 开始</c3> 
            <c4>## 第02章 Love Story</c4>
            <c5>"我爱你，"John对Mary轻声说道。</c5>

            ===== 严格遵守输出格式 ===== 
            <c1>第一段译文或空</c1> 
            <c2>第二段译文或空</c2> 
            ...
            """.strip())

        # --- 调用 LLM ---
        try:
            logging.info(f"🤖 开始翻译批次{batch_num}，内容长度: {len(tagged_eng)} 字符")
            llm_out = call_llm(system_prompt, tagged_eng)
            
            if not llm_out or not llm_out.strip():
                raise ValueError("LLM返回内容为空")
            
        except Exception as e:
            logging.error(f"批次{batch_num}翻译失败: {e}")
            # 创建错误占位符
            MISSING_DICT[batch_id] = ["翻译失败"]
            error_content = f"**翻译失败**: {e}\n\n原文:\n{raw_eng[:500]}...\n"
            
            batch_path = CHAP_DIR / f"{batch_id}.md"
            batch_path.write_text(error_content, encoding="utf-8")
            big_md_parts.append(error_content)
            
            logging.warning(f"批次{batch_num}已保存错误占位符")
            continue

        # --- 清洗 & 解析 ---
        try:
            cn_body, new_terms_block, miss = strip_tags(llm_out, keep_missing=True)
            MISSING_DICT[batch_id] = miss
            
            # 验证翻译质量
            if not cn_body.strip():
                raise ValueError("翻译结果为空")
            
            # 强化完整性检查
            original_segments = len(re.findall(r'<c\d+>', tagged_eng))
            # 计算最终译文的段落数（基于清洗后的内容）
            translated_segments = len([p for p in cn_body.split('\n\n') if p.strip()])
            
            # 检查每个输入段落是否都有对应的输出
            input_tags = set(re.findall(r'<c(\d+)>', tagged_eng))
            output_tags = set(re.findall(r'<c(\d+)>', llm_out))
            missing_tags = input_tags - output_tags
            
            # 打印详细的段落对比信息
            logging.info(f"📊 批次{batch_num}段落数量对比: 输入{original_segments}段 → 输出{translated_segments}段")
            
            if missing_tags:
                missing_list = sorted([int(tag) for tag in missing_tags])
                logging.error(f"🚨 批次{batch_num}发现遗漏段落: c{missing_list}")
                # 将遗漏的段落添加到缺失列表
                for tag_num in missing_list:
                    if f"c{tag_num:03d}" not in miss:
                        miss.append(f"c{tag_num:03d}")
                WARNING_DICT[batch_id] = f"遗漏段落: c{missing_list}"
            elif abs(original_segments - translated_segments) > original_segments * 0.2:  # 允许20%的差异
                warning_msg = f"原文{original_segments}段 vs 译文{translated_segments}段"
                logging.warning(f"⚠️  批次{batch_num}段落数量差异较大: {warning_msg}")
                WARNING_DICT[batch_id] = warning_msg
            elif original_segments != translated_segments:
                # 打印所有段落数量不一致的情况，即使差异在允许范围内
                diff_msg = f"原文{original_segments}段 vs 译文{translated_segments}段"
                logging.info(f"ℹ️  批次{batch_num}段落数量不一致: {diff_msg}")
            else:
                logging.info(f"✅ 批次{batch_num}段落完整性检查通过")
            
        except Exception as e:
            logging.error(f"批次{batch_num}结果解析失败: {e}")
            MISSING_DICT[batch_id] = ["解析失败"]
            cn_body = f"**解析失败**: {e}\n\n原始LLM输出:\n{llm_out[:1000]}..."
            new_terms_block = ""

        # --- 术语表处理已移除，不再处理术语表相关内容 ---

        # --- 写批次文件 ---
        try:
            batch_path = CHAP_DIR / f"{batch_id}.md"
            batch_content = f"{cn_body}\n"
            batch_path.write_text(batch_content, encoding="utf-8")
            big_md_parts.append(batch_content)
            
            # 验证文件写入
            if not batch_path.exists() or batch_path.stat().st_size == 0:
                raise IOError("文件写入失败或文件为空")
            
            logging.info(f"✅ 批次 {batch_num} 翻译完成 → {batch_path.name}")
            if miss:
                logging.warning(f"⚠️  批次 {batch_num} 有 {len(miss)} 个缺失段落")
            
        except Exception as e:
            logging.error(f"❌ 批次{batch_num}文件写入失败: {e}")
            raise
        
        # 术语表保存功能已移除
        
        # 适度限速
        time.sleep(1)
        
    except Exception as e:
        logging.error(f"处理批次{batch_num}时发生严重错误: {e}")
        # 记录错误但继续处理下一批次
        MISSING_DICT[batch_id] = [f"处理错误: {str(e)}"]
        continue

# ========= 汇总输出 ========= #
logging.info("=== 开始生成汇总报告 ===")

# 统计信息
processed_batches_success = len([bid for bid in MISSING_DICT if not any("处理错误" in str(m) for m in MISSING_DICT[bid])])  # 排除严重错误的批次
failed_batches = [bid for bid, miss_list in MISSING_DICT.items() if any("失败" in str(m) or "错误" in str(m) for m in miss_list)]
missing_segments = sum(len([m for m in miss_list if m != "翻译失败" and "错误" not in str(m)]) for miss_list in MISSING_DICT.values())

# 1. 术语表功能已移除
logging.info("术语表功能已禁用，专有名词通过prompt约束处理")

# 2. 缺失段落清单
try:
    missing_report = [
        "# 翻译质量报告",
        f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"总批次数: {total_batches}",
        f"成功处理: {processed_batches_success}",
        f"失败批次: {len(failed_batches)}",
        f"缺失段落: {missing_segments}",
        f"每批页数: {PAGES_PER_BATCH}",
        "",
        "## 详细信息"
    ]
    
    # 失败批次
    if failed_batches:
        missing_report.extend(["", "### 失败批次"])
        for bid in sorted(failed_batches):
            missing_report.append(f"- {bid}: {', '.join(MISSING_DICT[bid])}")
    
    # 缺失段落
    batches_with_missing = {bid: miss_list for bid, miss_list in MISSING_DICT.items() 
                           if miss_list and not any("失败" in str(m) or "错误" in str(m) for m in miss_list)}
    
    if batches_with_missing:
        missing_report.extend(["", "### 缺失段落"])
        for bid in sorted(batches_with_missing):
            if batches_with_missing[bid]:
                missing_report.append(f"- {bid}: {', '.join(batches_with_missing[bid])}")
    
    # 段落数量差异警告
    if WARNING_DICT:
        missing_report.extend(["", "### 段落数量差异警告"])
        for bid in sorted(WARNING_DICT):
            missing_report.append(f"- {bid}: {WARNING_DICT[bid]}")
    
    # 成功批次
    successful_batches = [bid for bid in MISSING_DICT if bid not in failed_batches and not MISSING_DICT[bid]]
    if successful_batches:
        missing_report.extend(["", "### 完全成功批次"])
        missing_report.append(f"共{len(successful_batches)}批次: {', '.join(sorted(successful_batches))}")
    
    missing_path = OUT_DIR / "translation_report.txt"
    missing_path.write_text("\n".join(missing_report), encoding="utf-8")
    logging.info(f"翻译报告已保存 → {missing_path}")
except Exception as e:
    logging.error(f"翻译报告生成失败: {e}")

# 3. 合并Markdown
try:
    if big_md_parts:
        # 添加文档头部
        header = f"""全文机翻  
更多泰百小说见 thaigl.drifting.boats

——————————

"""
        
        big_md_content = header + "\n".join(big_md_parts)
        big_md_path = OUT_DIR / BIG_MD_NAME
        big_md_path.write_text(big_md_content, encoding="utf-8")
        
        # 验证文件大小
        file_size = big_md_path.stat().st_size
        logging.info(f"全集 Markdown 汇总完成 → {big_md_path} ({file_size:,} 字节)")
    else:
        logging.warning("没有成功翻译的批次，跳过Markdown汇总")
except Exception as e:
    logging.error(f"Markdown汇总失败: {e}")

# 4. 最终统计
logging.info("=== 翻译流程完成 ===")
log_progress(total_batches, total_batches, "最终进度", "完成")
logging.info(f"✅ 处理结果: {processed_batches_success}/{total_batches} 批次成功")
if failed_batches:
    logging.warning(f"❌ 失败批次: {', '.join(failed_batches)}")
if missing_segments > 0:
    logging.warning(f"⚠️  总计缺失段落: {missing_segments}")
else:
    logging.info("🎉 所有段落翻译完成！")

# 5. 成本统计总结
if CONFIG.get('pricing', {}).get('enable_cost_tracking', False):
    pricing = CONFIG.get('pricing', {})
    currency = pricing.get('currency', 'USD')
    logging.info("=== 成本统计总结 ===")
    logging.info(f"📊 总Token使用: 输入{total_input_tokens:,} + 输出{total_output_tokens:,} = 总计{total_input_tokens + total_output_tokens:,}")
    logging.info(f"💰 总成本: {total_cost:.4f} {currency}")
    if total_input_tokens > 0:
        avg_cost_per_1k_input = (total_cost * 1000) / (total_input_tokens + total_output_tokens) if (total_input_tokens + total_output_tokens) > 0 else 0
        logging.info(f"📈 平均成本: {avg_cost_per_1k_input:.4f} {currency}/1K tokens")
else:
    logging.info("📊 Token统计: 输入{:,} + 输出{:,} = 总计{:,}".format(total_input_tokens, total_output_tokens, total_input_tokens + total_output_tokens))

# 6. 生成重试脚本（如果有失败批次）
if failed_batches:
    try:
        retry_config = CONFIG.copy()
        # 为失败的批次生成重试配置
        retry_batches = []
        for bid in failed_batches:
            if bid.startswith("batch_"):
                batch_num = int(bid.split("_")[1])
                p_start = (batch_num - 1) * PAGES_PER_BATCH + 1
                p_end = min(batch_num * PAGES_PER_BATCH, total_pages)
                retry_batches.append({"batch_num": batch_num, "pages": [p_start, p_end]})
        
        retry_config["failed_batches"] = retry_batches
        retry_config["pages_per_batch"] = PAGES_PER_BATCH
        
        retry_config_path = OUT_DIR / "retry_config.json"
        with open(retry_config_path, 'w', encoding='utf-8') as f:
            json.dump(retry_config, f, ensure_ascii=False, indent=2)
        
        logging.info(f"重试配置已生成 → {retry_config_path}")
        logging.info("可使用此配置重新运行脚本处理失败批次")
    except Exception as e:
        logging.warning(f"重试配置生成失败: {e}")
