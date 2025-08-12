#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重新翻译段落数量差异较大的批次

该脚本用于检测并重新翻译段落数量差异较大的批次，
解决原文段落数与译文段落数不匹配的问题。
"""

import json
import re
import textwrap
import logging
import time
import datetime
import requests
import os
import sys
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('retranslate.log', encoding='utf-8')
    ]
)

def load_config(config_path: str = "config.json") -> dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"配置文件 {config_path} 不存在")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"配置文件格式错误: {e}")
        sys.exit(1)

def call_llm(prompt_sys: str, prompt_user: str, config: dict, max_retries: int = 3) -> str:
    """调用LLM API"""
    headers = {
        "Authorization": f"Bearer {config['api']['API_KEY']}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": config['api']['LLM_MODEL'],
        "messages": [
            {"role": "system", "content": prompt_sys},
            {"role": "user", "content": prompt_user}
        ],
        "temperature": config['api'].get('temperature', 0.3),
        "max_tokens": 4000
    }
    
    for attempt in range(max_retries):
        try:
            logging.info(f"🤖 调用LLM API (尝试 {attempt + 1}/{max_retries})")
            response = requests.post(
                config['api']['API_URL'],
                headers=headers,
                json=data,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                logging.info(f"✅ API调用成功，返回内容长度: {len(content)} 字符")
                return content
            else:
                logging.error(f"API调用失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            logging.error(f"API调用异常: {e}")
            
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            logging.info(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
    
    raise Exception(f"API调用失败，已重试 {max_retries} 次")

def wrap_batch_with_tags(raw_text: str) -> str:
    """把批次原文按空行分段，加 <c1>…</c1> 标签，让LLM自行识别标题和页眉页码"""
    segments = [seg.strip() for seg in re.split(r"\n\s*\n", raw_text) if seg.strip()]
    tagged = []
    
    for idx, seg in enumerate(segments, start=1):
        # 不再预先标记标题，让LLM自行识别和处理
        tagged.append(f"<c{idx}>{seg}</c{idx}>")
    
    return "\n\n".join(tagged)

def count_segments(text: str) -> int:
    """统计文本中的段落数量"""
    # 如果文本包含标签，按标签计算
    if '<c' in text and '>' in text:
        return len(re.findall(r'<c\d+>', text))
    # 否则按非空行计算段落数
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return len(lines)

def analyze_batch_differences(output_dir: Path) -> List[Tuple[int, str, int, int]]:
    """分析批次文件，找出段落数量差异较大的批次"""
    chap_dir = output_dir / "chap_md"
    raw_content_dir = output_dir / "raw_content"
    
    if not chap_dir.exists():
        logging.error(f"翻译结果目录不存在: {chap_dir}")
        return []
    
    if not raw_content_dir.exists():
        logging.error(f"原始内容目录不存在: {raw_content_dir}")
        return []
    
    problem_batches = []
    
    # 遍历所有批次文件
    for batch_file in sorted(chap_dir.glob("batch_*.md")):
        batch_num = int(re.search(r'batch_(\d+)', batch_file.name).group(1))
        
        # 读取翻译结果
        try:
            translated_content = batch_file.read_text(encoding='utf-8')
            translated_segments = count_segments(translated_content)
        except Exception as e:
            logging.warning(f"读取批次 {batch_num} 翻译文件失败: {e}")
            continue
        
        # 读取原始文本
        raw_file = raw_content_dir / f"batch_{batch_num:03d}.txt"
        if not raw_file.exists():
            logging.warning(f"批次 {batch_num} 原始文件不存在: {raw_file}")
            continue
        
        try:
            raw_content = raw_file.read_text(encoding='utf-8')
            # 使用与translator.py相同的方式计算段落数
            tagged_content = wrap_batch_with_tags(raw_content)
            original_segments = count_segments(tagged_content)
        except Exception as e:
            logging.warning(f"读取批次 {batch_num} 原始文件失败: {e}")
            continue
        
        # 计算差异比例
        if original_segments > 0:
            diff_ratio = abs(original_segments - translated_segments) / original_segments
            
            # 如果差异超过20%或绝对差异超过10个段落，标记为问题批次
            if diff_ratio > 0.2 or abs(original_segments - translated_segments) > 10:
                problem_batches.append((
                    batch_num, 
                    batch_file.name, 
                    original_segments, 
                    translated_segments
                ))
                logging.warning(
                    f"⚠️  批次{batch_num}段落数量差异较大: "
                    f"原文{original_segments}段 vs 译文{translated_segments}段 "
                    f"(差异: {diff_ratio:.1%})"
                )
    
    return problem_batches

def retranslate_batch(batch_num: int, config: dict, output_dir: Path, glossary: Dict[str, str]) -> bool:
    """重新翻译指定批次"""
    raw_content_dir = output_dir / "raw_content"
    chap_dir = output_dir / "chap_md"
    
    # 读取原始文本
    raw_file = raw_content_dir / f"batch_{batch_num:03d}.txt"
    if not raw_file.exists():
        logging.error(f"批次 {batch_num} 原始文件不存在: {raw_file}")
        return False
    
    try:
        raw_content = raw_file.read_text(encoding='utf-8')
        # 使用与translator.py相同的方式计算段落数
        tagged_content = wrap_batch_with_tags(raw_content)
        original_segments = count_segments(tagged_content)
        logging.info(f"📖 开始重新翻译批次 {batch_num}，原文段落数: {original_segments}")
    except Exception as e:
        logging.error(f"读取批次 {batch_num} 原始文件失败: {e}")
        return False
    
    # 构建术语表
    gloss_block = "\n".join(f"{k}\t{v}" for k, v in glossary.items())
    
    # 构建系统提示词
    system_prompt = textwrap.dedent(f"""
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
        
        **重要提醒**：这是重新翻译任务，请特别注意段落对齐，确保每个 <cN> 标签都有对应的翻译输出。
    """)
    
    try:
        # 调用LLM进行翻译
        translated_content = call_llm(system_prompt, tagged_content, config)
        
        # 验证翻译结果
        translated_segments = count_segments(translated_content)
        
        logging.info(
            f"📝 批次 {batch_num} 重新翻译完成: "
            f"原文{original_segments}段 → 译文{translated_segments}段"
        )
        
        # 保存翻译结果
        output_file = chap_dir / f"batch_{batch_num:03d}.md"
        backup_file = chap_dir / f"batch_{batch_num:03d}.md.backup"
        
        # 备份原文件
        if output_file.exists():
            output_file.rename(backup_file)
            logging.info(f"💾 原翻译文件已备份为: {backup_file.name}")
        
        # 保存新翻译
        output_file.write_text(translated_content, encoding='utf-8')
        logging.info(f"✅ 批次 {batch_num} 重新翻译已保存")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ 批次 {batch_num} 重新翻译失败: {e}")
        return False

def load_glossary(glossary_path: Path) -> Dict[str, str]:
    """加载术语表"""
    glossary = {}
    if glossary_path.exists():
        try:
            content = glossary_path.read_text(encoding='utf-8')
            for line in content.strip().split('\n'):
                if '\t' in line:
                    key, value = line.split('\t', 1)
                    glossary[key.strip()] = value.strip()
            logging.info(f"📚 术语表已加载，共 {len(glossary)} 个条目")
        except Exception as e:
            logging.warning(f"加载术语表失败: {e}")
    return glossary

def merge_markdown(config: dict, output_dir: Path) -> bool:
    """合并翻译后的markdown文件为最终文档"""
    try:
        # 检查是否有chap_md目录（多书籍场景）
        chap_md_dir = output_dir / "chap_md"
        if chap_md_dir.exists():
            # 多书籍场景：从chap_md目录合并
            chap_files = sorted(glob.glob(str(chap_md_dir / "*.md")))
            big_md_path = output_dir / config['paths']['big_md_name']
        else:
            # 单书籍场景：从输出目录直接合并
            chap_files = sorted(glob.glob(str(output_dir / "*.md")))
            big_md_path = output_dir / config['paths']['big_md_name']
        
        if not chap_files:
            logging.warning("⚠️  未找到需要合并的markdown文件")
            return False
        
        logging.info(f"📝 开始合并 {len(chap_files)} 个markdown文件...")
        
        with open(big_md_path, "w", encoding="utf-8") as wf:
            for fp in chap_files:
                content = Path(fp).read_text(encoding="utf-8").strip()
                if content:
                    wf.write(content + "\n\n")
        
        logging.info(f"✅ 已生成整书 Markdown：{big_md_path}")
        return True
        
    except Exception as e:
        logging.error(f"❌ 合并markdown文件失败: {e}")
        return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='重新翻译段落差异较大的批次')
    parser.add_argument('--auto', action='store_true', help='自动模式，跳过交互式确认')
    args = parser.parse_args()
    
    print("🔄 重新翻译段落差异较大的批次")
    print("=" * 50)
    
    # 交互式获取输出目录
    output_dir = None
    if not args.auto:
        while True:
            output_input = input("请输入书籍目录路径 (例如: output/book1): ").strip()
            if output_input:
                output_dir = Path(output_input)
                if output_dir.exists() and output_dir.is_dir():
                    break
                else:
                    print(f"❌ 目录不存在: {output_input}")
                    continue
            else:
                print("❌ 请输入有效的目录路径")
                continue
    else:
        print("❌ 自动模式需要指定书籍目录路径")
        return
    
    # 从输出目录加载配置
    config_path = output_dir / "config.json"
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return
    
    config = load_config(str(config_path))
    logging.info(f"📚 使用书籍目录: {output_dir}")
    
    # 加载术语表
    glossary_path = output_dir / "glossary.tsv"
    glossary = load_glossary(glossary_path)
    
    # 分析问题批次
    logging.info("🔍 分析批次文件，查找段落数量差异较大的批次...")
    problem_batches = analyze_batch_differences(output_dir)
    
    if not problem_batches:
        logging.info("✅ 未发现段落数量差异较大的批次")
        return
    
    print(f"\n发现 {len(problem_batches)} 个问题批次:")
    for batch_num, filename, original, translated in problem_batches:
        diff_ratio = abs(original - translated) / original if original > 0 else 0
        print(f"  批次 {batch_num:3d}: {original:3d}段 → {translated:3d}段 (差异: {diff_ratio:.1%})")
    
    # 询问用户是否继续
    response = input(f"\n是否重新翻译这 {len(problem_batches)} 个批次? (y/N): ")
    if response.lower() not in ['y', 'yes', '是']:
        logging.info("用户取消操作")
        return
    
    # 重新翻译问题批次
    success_count = 0
    failed_batches = []
    
    for batch_num, filename, original, translated in problem_batches:
        logging.info(f"\n{'='*20} 处理批次 {batch_num} {'='*20}")
        
        if retranslate_batch(batch_num, config, output_dir, glossary):
            success_count += 1
        else:
            failed_batches.append(batch_num)
        
        # 添加延迟避免API限制
        time.sleep(2)
    
    # 输出结果统计
    print(f"\n{'='*50}")
    print(f"🎉 重新翻译完成!")
    print(f"✅ 成功: {success_count}/{len(problem_batches)} 个批次")
    
    if failed_batches:
        print(f"❌ 失败批次: {failed_batches}")
    
    logging.info(f"重新翻译任务完成: 成功 {success_count}, 失败 {len(failed_batches)}")
    
    # 如果有成功的重新翻译，自动合并markdown文件
    if success_count > 0:
        print(f"\n📚 正在重新生成整书markdown文件...")
        if merge_markdown(config, output_dir):
            print(f"🎊 整书markdown文件已更新!")
        else:
            print(f"⚠️  整书markdown文件更新失败，请手动运行 merge_md.py")

if __name__ == "__main__":
    main()