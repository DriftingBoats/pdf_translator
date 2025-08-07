#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chapter_translation_agent_cn.py
—— 章节级 PDF 英译本 → 中文译本批量翻译脚本
  • 按 config.json 中的页码区间切章
  • 送 LLM 翻译（维持原段落 <cN> 标签；缺失段输出 {{MISSING}}）
  • 增量更新术语表 glossary.tsv
  • 生成各章 md + 缺失段落清单 missing_list.txt
"""
import json, re, textwrap, logging, time, datetime, requests, os, sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from pdfminer.high_level import extract_text   # pip install pdfminer.six

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
        required_keys = ["api", "paths", "chapters"]
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

CHAPTER_MAP  = {cid: tuple(v) for cid, v in CONFIG["chapters"].items()}
GLOSS_CFG    = CONFIG.get("glossary", {})

# 验证PDF文件存在
if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF文件不存在: {PDF_PATH}")

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

# ========= 日志 ========= #
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")

# ========= 辅助函数 ========= #
def wrap_chapter_with_tags(raw_text: str) -> str:
    """把章节原文按空行分段，加 <c1>…</c1> 标签"""
    segments = [seg.strip() for seg in re.split(r"\n\s*\n", raw_text) if seg.strip()]
    tagged = []
    for idx, seg in enumerate(segments, start=1):
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
        else:
            clean_paras.append(p.strip())

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
            logging.debug(f"LLM调用尝试 {attempt+1}/{max_retries}")
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            
            result = resp.json()
            if "choices" not in result or not result["choices"]:
                raise ValueError("API返回格式错误：缺少choices字段")
            
            content = result["choices"][0]["message"]["content"]
            if not content or not content.strip():
                raise ValueError("API返回内容为空")
            
            logging.debug(f"LLM调用成功，返回内容长度: {len(content)}")
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
    logging.info(f"输出目录已准备: {OUT_DIR}")
except Exception as e:
    raise RuntimeError(f"创建输出目录失败: {e}")

gloss_path = OUT_DIR / "glossary.tsv"
GLOSSARY = load_glossary(gloss_path)
# 预置：config 中声明的词汇，优先级最高
GLOSSARY.update(GLOSS_CFG)
logging.info(f"术语表已加载，共{len(GLOSSARY)}个条目")

# ========= 解析整本 PDF ========= #
logging.info(f"开始加载PDF文件: {PDF_PATH}")
try:
    full_text = extract_text(str(PDF_PATH), page_numbers=None)   # 读全部文本
    if not full_text or not full_text.strip():
        raise ValueError("PDF文件内容为空或无法提取文本")
    
    pages = re.split(r"\f", full_text)                           # pdfminer 按 formfeed 分页
    if pages and pages[-1] == "":
        pages.pop()
    
    logging.info(f"PDF加载完成，共{len(pages)}页")
    
    # 验证章节页码范围
    max_page = len(pages)
    for chap_id, (p_start, p_end) in CHAPTER_MAP.items():
        if p_start < 1 or p_end > max_page or p_start > p_end:
            raise ValueError(f"章节{chap_id}页码范围无效: {p_start}-{p_end} (PDF共{max_page}页)")
    
except Exception as e:
    raise RuntimeError(f"PDF处理失败: {e}")

# ========= 主循环 ========= #
MISSING_DICT = {}
big_md_parts = []
total_chapters = len(CHAPTER_MAP)
processed_chapters = 0

# 创建进度日志
logging.info(f"开始处理{total_chapters}个章节")

for chap_id, (p_start, p_end) in CHAPTER_MAP.items():
    processed_chapters += 1
    logging.info(f"=== 处理章节 {chap_id} ({processed_chapters}/{total_chapters}) 页 {p_start}-{p_end} ===")
    
    try:
        raw_eng = "\n".join(pages[p_start-1:p_end])          # 页码从 1 开始
        
        if not raw_eng.strip():
            logging.warning(f"章节{chap_id}内容为空，跳过")
            MISSING_DICT[chap_id] = ["整章缺失"]
            continue
        
        tagged_eng = wrap_chapter_with_tags(raw_eng)
        
        # 检查标签数量是否合理
        tag_count = len(re.findall(r'<c\d+>', tagged_eng))
        if tag_count == 0:
            logging.warning(f"章节{chap_id}未能正确分段")
        else:
            logging.debug(f"章节{chap_id}分为{tag_count}个段落")

        # --- 获取风格信息 ---
        if not style_cache:
            # 使用当前章节的前几段作为风格分析样本
            sample_text = raw_eng[:10000]  # 取前10000字符作为样本
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

            3. **术语表**（glossary）  
            • 见下方《术语表》；若词条已列出，则在译文原样保留，不得译。  
            • 如遇新专有名词：**不要翻译使用原词 + 在 ```glossary``` 中标记**，脚本后续会增量写入术语表。

            4. **风格守则**  
            • 保持原文风格特征：{style_cache}
            • 标点：用中文标点，英文专名内部保留半角。  
            • 数字、计量单位、货币符号照原文。
            • 保持原文的叙事节奏、语调和情感表达方式。

            =============== 术语表（供参考） ===============
            {gloss_block}

            ===== 输出格式（严格遵守，不得添加多余标记） =====
            <c1>第一段译文</c1>
            <c2>第二段译文</c2>
            ...
            ```glossary
            新词1⇢译词1
            新词2⇢译词2
            ```
            """.strip())

        # --- 调用 LLM ---
        try:
            logging.debug(f"开始翻译章节{chap_id}，内容长度: {len(tagged_eng)}")
            llm_out = call_llm(system_prompt, tagged_eng)
            
            if not llm_out or not llm_out.strip():
                raise ValueError("LLM返回内容为空")
            
        except Exception as e:
            logging.error(f"章节{chap_id}翻译失败: {e}")
            # 创建错误占位符
            MISSING_DICT[chap_id] = ["翻译失败"]
            error_content = f"## {chap_id}\n\n**翻译失败**: {e}\n\n原文:\n{raw_eng[:500]}...\n"
            
            chap_path = CHAP_DIR / f"{chap_id}.md"
            chap_path.write_text(error_content, encoding="utf-8")
            big_md_parts.append(error_content)
            
            logging.warning(f"章节{chap_id}已保存错误占位符")
            continue

        # --- 清洗 & 解析 ---
        try:
            cn_body, new_terms_block, miss = strip_tags(llm_out, keep_missing=True)
            MISSING_DICT[chap_id] = miss
            
            # 验证翻译质量
            if not cn_body.strip():
                raise ValueError("翻译结果为空")
            
            # 检查段落数量是否合理
            original_segments = len(re.findall(r'<c\d+>', tagged_eng))
            translated_segments = len(re.findall(r'<c\d+>', llm_out))
            
            if abs(original_segments - translated_segments) > original_segments * 0.2:  # 允许20%的差异
                logging.warning(f"章节{chap_id}段落数量差异较大: 原文{original_segments}段 vs 译文{translated_segments}段")
            
        except Exception as e:
            logging.error(f"章节{chap_id}结果解析失败: {e}")
            MISSING_DICT[chap_id] = ["解析失败"]
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
                logging.info(f"章节{chap_id}新增{new_terms_count}个术语")
                
        except Exception as e:
            logging.warning(f"章节{chap_id}术语表更新失败: {e}")

        # --- 写章节文件 ---
        try:
            chap_path = CHAP_DIR / f"{chap_id}.md"
            chapter_content = f"## {chap_id}\n\n{cn_body}\n"
            chap_path.write_text(chapter_content, encoding="utf-8")
            big_md_parts.append(chapter_content)
            
            # 验证文件写入
            if not chap_path.exists() or chap_path.stat().st_size == 0:
                raise IOError("文件写入失败或文件为空")
            
            logging.info(f"章节 {chap_id} 完成 → {chap_path.name} (缺段 {len(miss)})")
            
        except Exception as e:
            logging.error(f"章节{chap_id}文件写入失败: {e}")
            raise
        
        # 保存进度（每处理完一章就保存术语表）
        try:
            save_glossary(GLOSSARY, gloss_path)
        except Exception as e:
            logging.warning(f"术语表保存失败: {e}")
        
        # 适度限速
        time.sleep(1)
        
    except Exception as e:
        logging.error(f"处理章节{chap_id}时发生严重错误: {e}")
        # 记录错误但继续处理下一章节
        MISSING_DICT[chap_id] = [f"处理错误: {str(e)}"]
        continue

# ========= 汇总输出 ========= #
logging.info("开始生成汇总报告...")

# 统计信息
total_chapters = len(CHAPTER_MAP)
processed_chapters = len([cid for cid in MISSING_DICT if not any("处理错误" in str(m) for m in MISSING_DICT[cid])])  # 排除严重错误的章节
failed_chapters = [cid for cid, miss_list in MISSING_DICT.items() if any("失败" in str(m) or "错误" in str(m) for m in miss_list)]
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
        f"总章节数: {total_chapters}",
        f"成功处理: {processed_chapters}",
        f"失败章节: {len(failed_chapters)}",
        f"缺失段落: {missing_segments}",
        "",
        "## 详细信息"
    ]
    
    # 失败章节
    if failed_chapters:
        missing_report.extend(["", "### 失败章节"])
        for cid in sorted(failed_chapters):
            missing_report.append(f"- {cid}: {', '.join(MISSING_DICT[cid])}")
    
    # 缺失段落
    chapters_with_missing = {cid: miss_list for cid, miss_list in MISSING_DICT.items() 
                           if miss_list and not any("失败" in str(m) or "错误" in str(m) for m in miss_list)}
    
    if chapters_with_missing:
        missing_report.extend(["", "### 缺失段落"])
        for cid in sorted(chapters_with_missing):
            if chapters_with_missing[cid]:
                missing_report.append(f"- {cid}: {', '.join(chapters_with_missing[cid])}")
    
    # 成功章节
    successful_chapters = [cid for cid in MISSING_DICT if cid not in failed_chapters and not MISSING_DICT[cid]]
    if successful_chapters:
        missing_report.extend(["", "### 完全成功章节"])
        missing_report.append(f"共{len(successful_chapters)}章: {', '.join(sorted(successful_chapters))}")
    
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
> 总章节: {total_chapters} | 成功: {processed_chapters} | 失败: {len(failed_chapters)}

---

"""
        
        big_md_content = header + "\n".join(big_md_parts)
        big_md_path = OUT_DIR / BIG_MD_NAME
        big_md_path.write_text(big_md_content, encoding="utf-8")
        
        # 验证文件大小
        file_size = big_md_path.stat().st_size
        logging.info(f"全集 Markdown 汇总完成 → {big_md_path} ({file_size:,} 字节)")
    else:
        logging.warning("没有成功翻译的章节，跳过Markdown汇总")
except Exception as e:
    logging.error(f"Markdown汇总失败: {e}")

# 4. 最终统计
logging.info("=== 翻译流程完成 ===")
logging.info(f"处理结果: {processed_chapters}/{total_chapters} 章节成功")
if failed_chapters:
    logging.warning(f"失败章节: {', '.join(failed_chapters)}")
if missing_segments > 0:
    logging.warning(f"总计缺失段落: {missing_segments}")
else:
    logging.info("所有段落翻译完成！")

# 5. 生成重试脚本（如果有失败章节）
if failed_chapters:
    try:
        retry_config = CONFIG.copy()
        retry_config["chapters"] = {cid: CHAPTER_MAP[cid] for cid in failed_chapters}
        
        retry_config_path = OUT_DIR / "retry_config.json"
        with open(retry_config_path, 'w', encoding='utf-8') as f:
            json.dump(retry_config, f, ensure_ascii=False, indent=2)
        
        logging.info(f"重试配置已生成 → {retry_config_path}")
        logging.info("可使用此配置重新运行脚本处理失败章节")
    except Exception as e:
        logging.warning(f"重试配置生成失败: {e}")
