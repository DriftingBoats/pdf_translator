#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from pathlib import Path

# 正则表达式模式
TAG_PAT = re.compile(r"<c\d+>(.*?)</c\d+>", re.S)
NEWTERM_PAT = re.compile(r"```glossary(.*?)```", re.S)

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

def clean_batch_file(batch_num: int, output_dir: Path):
    """清理指定批次文件的标签"""
    chap_dir = output_dir / "chap_md"
    batch_file = chap_dir / f"batch_{batch_num:03d}.md"
    
    if not batch_file.exists():
        print(f"❌ 批次文件不存在: {batch_file}")
        return False
    
    # 读取原文件内容
    try:
        content = batch_file.read_text(encoding='utf-8')
        print(f"📖 读取批次 {batch_num} 文件，长度: {len(content)} 字符")
    except Exception as e:
        print(f"❌ 读取批次 {batch_num} 文件失败: {e}")
        return False
    
    # 检查是否包含标签
    if not re.search(r'<c\d+>', content):
        print(f"✅ 批次 {batch_num} 已经没有标签，跳过处理")
        return True
    
    # 清理标签
    try:
        clean_content, new_terms, miss_list = strip_tags(content, keep_missing=True)
        
        if not clean_content.strip():
            print(f"❌ 批次 {batch_num} 清理后内容为空")
            return False
        
        # 备份原文件
        backup_file = chap_dir / f"batch_{batch_num:03d}.md.backup"
        if not backup_file.exists():
            batch_file.rename(backup_file)
            print(f"💾 原文件已备份为: {backup_file.name}")
        
        # 保存清理后的内容
        batch_file.write_text(clean_content, encoding='utf-8')
        print(f"✅ 批次 {batch_num} 标签已清理，内容已保存")
        
        if miss_list:
            print(f"⚠️  批次 {batch_num} 有 {len(miss_list)} 个缺失段落: {', '.join(miss_list)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 清理批次 {batch_num} 失败: {e}")
        return False

def main():
    """主函数"""
    output_dir = Path("output/god2")
    
    if not output_dir.exists():
        print(f"❌ 目录不存在: {output_dir}")
        return
    
    # 要处理的批次
    batches_to_clean = [3, 4, 6]
    
    print("🧹 开始清理指定批次的标签")
    print("=" * 50)
    
    success_count = 0
    for batch_num in batches_to_clean:
        print(f"\n处理批次 {batch_num}:")
        if clean_batch_file(batch_num, output_dir):
            success_count += 1
    
    print(f"\n{'='*50}")
    print(f"🎉 处理完成！")
    print(f"✅ 成功: {success_count}/{len(batches_to_clean)} 个批次")
    
    if success_count > 0:
        print(f"\n📚 建议重新生成整书markdown文件")

if __name__ == "__main__":
    main()