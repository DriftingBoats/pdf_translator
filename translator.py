#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
page_batch_translation_agent_cn.py
—— 按页数分批 PDF 英译本 → 中文译本批量翻译脚本
  • 按指定页数X自动分批翻译
  • 处理句子完整性，确保翻译至句子结束
  • 自动识别标题并保持格式
  • 自动编号并最终整合为一个文件
  • 增量更新术语表 glossary.tsv
"""
import json, re, textwrap, logging, time, datetime, requests, os, sys, warnings
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 过滤pdfminer的字体警告信息
warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")

from pdfminer.high_level import extract_text   # pip install pdfminer.six

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
GLOSS_CFG    = CONFIG.get("glossary", {})

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
NEWTERM_PAT = re.compile(r"```glossary(.*?)```", re.S)

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

def ensure_sentence_completion(text: str) -> str:
    """确保文本以完整句子结束"""
    text = text.strip()
    if not text:
        return text
    
    # 检查是否以句号、问号、感叹号结尾
    if text[-1] in '.!?':
        return text
    
    # 查找最后一个完整句子的结束位置
    last_sentence_end = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in '.!?':
            # 确保不是缩写（如Mr. Dr.等）
            if i < len(text) - 1 and text[i+1] in ' \n\t':
                last_sentence_end = i
                break
            elif i == len(text) - 1:
                last_sentence_end = i
                break
    
    if last_sentence_end > 0:
        return text[:last_sentence_end + 1]
    
    return text

def wrap_batch_with_tags(raw_text: str) -> str:
    """把批次原文按空行分段，加 <c1>…</c1> 标签，让LLM自行识别标题和页眉页码"""
    segments = [seg.strip() for seg in re.split(r"\n\s*\n", raw_text) if seg.strip()]
    tagged = []
    
    for idx, seg in enumerate(segments, start=1):
        # 不再预先标记标题，让LLM自行识别和处理
        tagged.append(f"<c{idx}>{seg}</c{idx}>")
    
    return "\n\n".join(tagged)

def strip_tags(llm_output: str, keep_missing: bool = True):
    """清洗 LLM 输出 & 收集缺失段"""
    paragraphs = TAG_PAT.findall(llm_output)

    miss_list, clean_paras = [], []
    for idx, p in enumerate(paragraphs, start=1):
        if p.strip() == "{{MISSING}}":
            miss_list.append(f"c{idx:03d}")
            if keep_missing:
                clean_paras.append("{{MISSING}}")
        elif p.strip() == "" or p.strip().startswith("[页眉页脚]") or p.strip().startswith("[目录]"):  # 处理空标签和特殊标记
            # 跳过空内容和页眉页脚、目录标记，不添加到clean_paras中
            pass
        else:
            clean_paras.append(p.strip())

    # 过滤掉空字符串，避免多余的空行
    clean_paras = [para for para in clean_paras if para.strip()]
    pure_text = "\n\n".join(clean_paras)
    new_terms_block = "\n".join(
        line.strip()
        for blk in NEWTERM_PAT.findall(llm_output)
        for line in blk.strip().splitlines() if line.strip()
    )
    return pure_text, new_terms_block, miss_list

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

def load_glossary(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            src, tgt = line.split("\t", 1)
            out[src.strip()] = tgt.strip()
    return out

def save_glossary(gls: Dict[str,str], path: Path):
    lines = [f"{k}\t{v}" for k, v in sorted(gls.items())]
    path.write_text("\n".join(lines), encoding="utf-8")

def call_llm(prompt_sys: str, prompt_user: str, max_retries: int = 3, timeout: int = 120) -> str:
    """调用LLM API，带重试和错误处理"""
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
            
            # 记录token使用情况（如果可用）
            if "usage" in result and result["usage"]:
                usage = result["usage"]
                logging.info(f"📊 Token使用: 输入{usage.get('prompt_tokens', 0)} + 输出{usage.get('completion_tokens', 0)} = 总计{usage.get('total_tokens', 0)}")
            
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

gloss_path = OUT_DIR / "glossary.tsv"
GLOSSARY = load_glossary(gloss_path)
# 预置：config 中声明的词汇，优先级最高
GLOSSARY.update(GLOSS_CFG)
logging.info(f"术语表已加载，共{len(GLOSSARY)}个条目")

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
    
    full_text = extract_text(str(pdf_path), page_numbers=None)
    
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
    
    pages = re.split(r"\f", full_text)                           # pdfminer 按 formfeed 分页
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
        
        # 检查句子完整性，如果不是最后一批且句子未完整，尝试扩展
        if batch_num < total_batches:
            # 检查是否需要扩展到下一页以完成句子
            completed_text = ensure_sentence_completion(raw_eng)
            if len(completed_text) < len(raw_eng) * 0.8:  # 如果截断太多，尝试扩展
                if p_end < total_pages:
                    # 添加下一页的部分内容直到句子完整
                    next_page_text = pages[p_end] if p_end < len(pages) else ""
                    extended_text = raw_eng + "\n" + next_page_text
                    completed_extended = ensure_sentence_completion(extended_text)
                    if len(completed_extended) > len(completed_text):
                        raw_eng = completed_extended
                        logging.info(f"📝 批次{batch_num}扩展到下一页以完成句子")
            else:
                raw_eng = completed_text
        
        tagged_eng = wrap_batch_with_tags(raw_eng)
        
        # 检查标签数量是否合理
        tag_count = len(re.findall(r'<c\d+>', tagged_eng))
        if tag_count == 0:
            logging.warning(f"⚠️  批次{batch_num}未能正确分段")
        else:
            logging.info(f"📝 批次{batch_num}分为{tag_count}个段落，文本长度: {len(raw_eng)} 字符")

        # --- 获取风格信息 ---
        if not style_cache:
            # 使用当前批次的前几段作为风格分析样本
            sample_text = raw_eng[:5000]  # 取前5000字符作为样本
            refresh_style(sample_text)
        
        # --- 构造系统提示 ---
        gloss_block = "\n".join(f"{k}\t{v}" for k,v in GLOSSARY.items())
        system_prompt = textwrap.dedent( f"""
            你是一名 <资深文学译者>，需把下方【泰语→英译→中文】的英文小说精准、逐句地译成现代中文。

            ================ 任务要求 ================
            1. **逐段落对齐**  
            • 源英文用 <cN>…</cN> 标签包裹（脚本已自动加）。  
            • 你必须为 *每一个* <cN> 段落输出对应 <cN> 段落，保持顺序一致。  
            • 绝不可合并、增删或跳过段落。若确实无法翻译，原文用 <cN>{{{{MISSING}}}}</cN> 原样抄写。

            2. **不省略**  
            • 译文行数 ≈ 源行数。  
            • 结尾自行执行检查：若发现有未输出的 <cX> 段，必须补上 <cX>{{{{MISSING}}}}</cX>。

            3. **智能识别与处理**（重要！）
            • **页眉页脚标记**：遇到以下内容输出特殊标记 <cN>[页眉页脚]</cN>：
              - 页码信息（如"Page 1 of 506"、"第1页/共506页"等）
              - 作者信息重复（如邮箱地址、作者名重复出现）
              - 网站链接、版权信息
              - 明显的页眉页脚重复内容
            • **章节标题识别**：识别以下内容并转换为Markdown格式：
              - 章节标题 → ## 标题
              - 小节标题 → ### 标题  
              - "Chapter X"、"第X章" → ## 第X章
              - 居中的短标题 → ### 标题
            • **特殊内容处理**：
              - 作者的话、前言、后记等 → ## 作者的话
              - 目录、索引等 → [目录]

            4. **术语表**（glossary）  
            • 见下方《术语表》；若词条已列出，则在译文原样保留，不得译。  
            • 如遇新专有名词（人名、地名、品牌名等）：**在译文中保持原词不翻译，并在 ```glossary``` 中按格式 原词⇢原词 标记**，脚本后续会增量写入术语表。
            • 注意：专有名词应保持原文，不要翻译成中文。

            5. **风格守则**  
            • 保持原文风格特征：{style_cache}
            • **第三人称改第一人称**：泰语转译中常见用第三人称称呼自己的对话，必须改成第一人称以符合中文阅读习惯（此规则优先级高于术语表保留原词）。
            • **标点规范**：用中文标点，英文专名内部保留半角。禁止出现多个连续句号（如。。。、.。。。、.。.等），统一使用省略号……。  
            • 数字、计量单位、货币符号照原文。
            • 保持原文的叙事节奏、语调和情感表达方式。

            =============== 术语表（供参考） ===============
            {gloss_block}

            ===== 输出格式示例 =====
            输入：
            <c1>Page 1 of 506</c1>
            <c2>Author Name</c2>
            <c3>Chapter 1: The Beginning</c3>
            <c4>It was a dark and stormy night...</c4>
            
            输出：
            <c1>[页眉页脚]</c1>
            <c2>[页眉页脚]</c2>
            <c3># 第一章：开始</c3>
            <c4>那是一个黑暗而暴风雨的夜晚……</c4>
            
            ===== 严格遵守输出格式 =====
            <c1>第一段译文或空</c1>
            <c2>第二段译文或空</c2>
            ...
            ```glossary
            专有名词1⇢专有名词1
            专有名词2⇢专有名词2
            ```
            
            **专有名词处理示例**：
            - 人名 "John Smith" → 译文中保持 "John Smith"，术语表中添加 "John Smith⇢John Smith"
            - 地名 "Bangkok" → 译文中保持 "Bangkok"，术语表中添加 "Bangkok⇢Bangkok"
            - 品牌 "iPhone" → 译文中保持 "iPhone"，术语表中添加 "iPhone⇢iPhone"
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
            
            # 检查段落数量是否合理
            original_segments = len(re.findall(r'<c\d+>', tagged_eng))
            translated_segments = len(re.findall(r'<c\d+>', llm_out))
            
            if abs(original_segments - translated_segments) > original_segments * 0.2:  # 允许20%的差异
                warning_msg = f"原文{original_segments}段 vs 译文{translated_segments}段"
                logging.warning(f"批次{batch_num}段落数量差异较大: {warning_msg}")
                WARNING_DICT[batch_id] = warning_msg
            
        except Exception as e:
            logging.error(f"批次{batch_num}结果解析失败: {e}")
            MISSING_DICT[batch_id] = ["解析失败"]
            cn_body = f"**解析失败**: {e}\n\n原始LLM输出:\n{llm_out[:1000]}..."
            new_terms_block = ""

        # --- 更新术语表 ---
        try:
            new_terms_count = 0
            for line in new_terms_block.splitlines():
                if "\t" in line or "⇢" in line:
                    # 支持两种格式：制表符分隔或箭头分隔
                    if "⇢" in line:
                        src, tgt = [x.strip() for x in line.split("⇢", 1)]
                    else:
                        src, tgt = [x.strip() for x in line.split("\t", 1)]
                    
                    if src and tgt and src not in GLOSSARY:
                        GLOSSARY[src] = tgt
                        new_terms_count += 1
            
            if new_terms_count > 0:
                logging.info(f"📚 批次{batch_num}新增{new_terms_count}个术语")
                
        except Exception as e:
            logging.warning(f"⚠️  批次{batch_num}术语表更新失败: {e}")

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
        
        # 保存进度（每处理完一章就保存术语表）
        try:
            save_glossary(GLOSSARY, gloss_path)
        except Exception as e:
            logging.warning(f"术语表保存失败: {e}")
        
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

# 1. 术语表
try:
    save_glossary(GLOSSARY, gloss_path)
    logging.info(f"术语表已更新 → {gloss_path} (共{len(GLOSSARY)}个条目)")
except Exception as e:
    logging.error(f"术语表保存失败: {e}")

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
        header = f"""# 翻译文档

> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 总批次: {total_batches} | 成功: {processed_batches_success} | 失败: {len(failed_batches)}
> 每批页数: {PAGES_PER_BATCH} | 总页数: {total_pages}

---

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

# 5. 生成重试脚本（如果有失败批次）
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
