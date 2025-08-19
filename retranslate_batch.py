#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速重新翻译指定批次

用法:
  python retranslate_batch.py 9           # 重新翻译批次9
  python retranslate_batch.py 9 12 15     # 重新翻译批次9、12、15
  python retranslate_batch.py --all-diff  # 重新翻译所有差异较大的批次
"""

import json
import re
import textwrap
import logging
import time
import requests
import sys
import argparse
import glob
from pathlib import Path
from typing import Dict, List

# 正则表达式模式
TAG_PAT = re.compile(r'<c\d+>(.*?)</c\d+>', re.DOTALL)
NEWTERM_PAT = re.compile(r'```glossary\s*\n(.*?)\n```', re.DOTALL | re.IGNORECASE)

# 设置简洁的日志格式
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)

def load_config(config_path: str = "config.json") -> dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"❌ 配置文件 {config_path} 不存在")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"❌ 配置文件格式错误: {e}")
        sys.exit(1)

def call_llm(prompt_sys: str, prompt_user: str, config: dict) -> str:
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
    
    try:
        response = requests.post(
            config['api']['API_URL'],
            headers=headers,
            json=data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API调用失败: {response.status_code} - {response.text}")
            
    except Exception as e:
        raise Exception(f"API调用异常: {e}")

def wrap_batch_with_tags(raw_text: str) -> str:
    """把批次原文按空行分段，加 <c1>…</c1> 标签，让LLM自行识别标题和页眉页码"""
    segments = [seg.strip() for seg in re.split(r"\n\s*\n", raw_text) if seg.strip()]
    tagged = []
    
    for idx, seg in enumerate(segments, start=1):
        # 不再预先标记标题，让LLM自行识别和处理
        tagged.append(f"<c{idx}>{seg}</c{idx}>")
    
    return "\n\n".join(tagged)

def count_segments(text: str) -> int:
    """计算文本中的段落数量"""
    # 如果文本包含标签，按标签计算
    if '<c' in text and '>' in text:
        return len(re.findall(r'<c\d+>', text))
    # 否则按非空行计算段落数
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return len(lines)

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

def find_diff_batches(output_dir: Path, threshold: float = 0.2) -> List[int]:
    """查找段落数量差异较大的批次"""
    chap_dir = output_dir / "chap_md"
    raw_content_dir = output_dir / "raw_content"
    
    problem_batches = []
    
    for batch_file in sorted(chap_dir.glob("batch_*.md")):
        batch_num = int(re.search(r'batch_(\d+)', batch_file.name).group(1))
        
        try:
            # 读取翻译结果
            translated_content = batch_file.read_text(encoding='utf-8')
            translated_segments = count_segments(translated_content)
            
            # 读取原始文本
            raw_file = raw_content_dir / f"batch_{batch_num:03d}.txt"
            if raw_file.exists():
                raw_content = raw_file.read_text(encoding='utf-8')
                original_segments = count_segments(raw_content)
                
                # 计算差异比例
                if original_segments > 0:
                    diff_ratio = abs(original_segments - translated_segments) / original_segments
                    if diff_ratio > threshold:
                        problem_batches.append(batch_num)
                        
        except Exception:
            continue
    
    return sorted(problem_batches)

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
        except Exception:
            pass
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
            # 添加自定义头部
            wf.write("全文机翻  \n更多泰百小说见 `https://thaigl.drifting.boats/`\n\n---\n\n")
            
            for fp in chap_files:
                content = Path(fp).read_text(encoding="utf-8").strip()
                if content:
                    wf.write(content + "\n\n")
        
        logging.info(f"✅ 已生成整书 Markdown：{big_md_path}")
        return True
        
    except Exception as e:
        logging.error(f"❌ 合并markdown文件失败: {e}")
        return False

def retranslate_batch(batch_num: int, config: dict, output_dir: str, glossary: Dict[str, str]) -> bool:
    """重新翻译指定批次"""
    output_path = Path(output_dir)
    raw_content_dir = output_path / "raw_content"
    chap_dir = output_path / "chap_md"
    
    # 读取原始文本
    raw_file = raw_content_dir / f"batch_{batch_num:03d}.txt"
    if not raw_file.exists():
        logging.error(f"❌ 批次 {batch_num} 原始文件不存在")
        return False
    
    try:
        raw_content = raw_file.read_text(encoding='utf-8')
        # 使用与translator.py相同的方式计算段落数
        tagged_content = wrap_batch_with_tags(raw_content)
        original_segments = count_segments(tagged_content)
        logging.info(f"📖 开始重新翻译批次 {batch_num} (原文 {original_segments} 段)")
    except Exception as e:
        logging.error(f"❌ 读取批次 {batch_num} 失败: {e}")
        return False
    
    # 构建术语表
    gloss_block = "\n".join(f"{k}\t{v}" for k, v in glossary.items())
    
    # 构建系统提示词（简化版）
    system_prompt = textwrap.dedent(f"""
        你是一名资深文学译者，需要将英文小说精准翻译成中文。

        **核心要求**：
        1. 逐段落对齐：每个 <cN> 标签必须有对应的翻译输出
        2. 不能合并、删除或跳过任何段落
        3. 如果无法翻译，用 <cN>{{{{MISSING}}}}</cN> 标记
        4. 页眉页脚用 <cN>[页眉页脚]</cN> 标记
        5. 章节标题转换为 Markdown 格式
        6. 专有名词保持原文，在术语表中标记

        **术语表**：
        {gloss_block}

        **输出格式**：
        <c1>第一段译文</c1>
        <c2>第二段译文</c2>
        ...
        ```glossary
        新专有名词⇢新专有名词
        ```
    """)
    
    try:
        # 调用LLM
        logging.info(f"🤖 调用API翻译批次 {batch_num}...")
        llm_output = call_llm(system_prompt, tagged_content, config)
        
        if not llm_output or not llm_output.strip():
            raise ValueError("LLM返回内容为空")
        
        # 清洗输出并去除标签
        cn_body, new_terms_block, miss_list = strip_tags(llm_output, keep_missing=True)
        
        # 验证翻译质量
        if not cn_body.strip():
            raise ValueError("翻译结果为空")
        
        # 检查段落数量是否合理
        translated_segments = len(re.findall(r'<c\d+>', llm_output))
        logging.info(f"📝 翻译完成: {original_segments} 段 → {translated_segments} 段")
        
        if abs(original_segments - translated_segments) > original_segments * 0.2:  # 允许20%的差异
            warning_msg = f"原文{original_segments}段 vs 译文{translated_segments}段"
            logging.warning(f"⚠️  批次{batch_num}段落数量差异较大: {warning_msg}")
        
        # 更新术语表
        if new_terms_block:
            new_terms_count = 0
            for line in new_terms_block.splitlines():
                if "\t" in line or "⇢" in line:
                    # 支持两种格式：制表符分隔或箭头分隔
                    if "⇢" in line:
                        src, tgt = [x.strip() for x in line.split("⇢", 1)]
                    else:
                        src, tgt = [x.strip() for x in line.split("\t", 1)]
                    
                    if src and tgt and src not in glossary:
                        glossary[src] = tgt
                        new_terms_count += 1
            
            if new_terms_count > 0:
                logging.info(f"📚 批次{batch_num}新增{new_terms_count}个术语")
                # 保存更新的术语表
                glossary_path = output_path / "glossary.tsv"
                with open(glossary_path, 'w', encoding='utf-8') as f:
                    for k, v in glossary.items():
                        f.write(f"{k}\t{v}\n")
        
        # 备份并保存清洗后的内容
        output_file = chap_dir / f"batch_{batch_num:03d}.md"
        if output_file.exists():
            backup_file = chap_dir / f"batch_{batch_num:03d}.md.backup"
            output_file.rename(backup_file)
            logging.info(f"💾 原文件已备份")
        
        output_file.write_text(cn_body, encoding='utf-8')
        
        if miss_list:
            logging.warning(f"⚠️  批次{batch_num}有{len(miss_list)}个缺失段落: {', '.join(miss_list)}")
        
        logging.info(f"✅ 批次 {batch_num} 重新翻译完成")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ 批次 {batch_num} 翻译失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='重新翻译指定批次')
    parser.add_argument('--auto', action='store_true', help='自动模式，跳过交互式提示')
    
    args = parser.parse_args()
    
    # 交互式获取输出目录
    output_dir = None
    if not args.auto:
        print("🔄 重新翻译工具")
        print("=" * 30)
        
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
    
    # 交互式获取批次
    batches = []
    all_diff = False
    
    if not args.auto:
        print("\n请选择操作方式:")
        print("1. 重新翻译指定批次")
        print("2. 重新翻译所有差异较大的批次")
        print("3. 查看帮助信息")
        print("4. 退出")
        
        while True:
            choice = input("\n请输入选项 (1-4): ").strip()
            
            if choice == '1':
                batch_input = input("请输入要重新翻译的批次号 (用空格分隔多个批次): ").strip()
                if batch_input:
                    try:
                        batches = [int(x) for x in batch_input.split()]
                        break
                    except ValueError:
                        print("❌ 批次号必须是数字，请重新输入")
                        continue
                else:
                    print("❌ 请输入至少一个批次号")
                    continue
            elif choice == '2':
                all_diff = True
                break
            elif choice == '3':
                parser.print_help()
                return
            elif choice == '4':
                print("👋 已退出")
                return
            else:
                print("❌ 无效选项，请输入 1-4")
                continue
    
    # 加载术语表
    glossary_path = output_dir / "glossary.tsv"
    glossary = load_glossary(glossary_path)
    
    # 确定要处理的批次
    if all_diff:
        batches = find_diff_batches(output_dir)
        if not batches:
            print("✅ 未发现差异较大的批次")
            return
        print(f"🔍 发现 {len(batches)} 个差异较大的批次: {batches}")
    
    # 重新翻译
    success_count = 0
    for i, batch_num in enumerate(batches, 1):
        print(f"\n{'='*10} 处理批次 {batch_num} ({i}/{len(batches)}) {'='*10}")
        
        if retranslate_batch(batch_num, config, str(output_dir), glossary):
            success_count += 1
        
        # API调用间隔
        if i < len(batches):
            time.sleep(2)
    
    # 结果统计
    print(f"\n🎉 处理完成: {success_count}/{len(batches)} 个批次成功")
    
    # 如果有成功的重新翻译，自动合并markdown文件
    if success_count > 0:
        print(f"\n📚 正在重新生成整书markdown文件...")
        if merge_markdown(config, output_dir):
            print(f"🎊 整书markdown文件已更新!")
        else:
            print(f"⚠️  整书markdown文件更新失败，请手动运行 merge_md.py")

if __name__ == "__main__":
    main()