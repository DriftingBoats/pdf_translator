#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 outputs/book_title/*.md 按文件名顺序合并为 big_md_name
"""
import json, glob, sys
from pathlib import Path

def main():
    # 获取书籍目录参数
    if len(sys.argv) > 1:
        book_dir = Path(sys.argv[1])
    else:
        book_dir = Path(".")
    
    # 确保目录存在
    if not book_dir.exists():
        print(f"❌ 目录不存在: {book_dir}")
        return
    
    # 读取配置文件
    config_path = book_dir / "config.json"
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return
    
    try:
        CFG = json.load(open(config_path, encoding="utf-8"))
        BIG_MD = book_dir / CFG["paths"]["big_md_name"]
        
        # 查找章节文件
        chap_dir = book_dir / "chap_md"
        if chap_dir.exists():
            chap_files = sorted(glob.glob(str(chap_dir / "batch_*.md")))
        else:
            chap_files = sorted(glob.glob(str(book_dir / "batch_*.md")))
        
        if not chap_files:
            print(f"❌ 未找到章节文件")
            return
        
        print(f"📝 开始合并 {len(chap_files)} 个markdown文件...")
        
        with open(BIG_MD, "w", encoding="utf-8") as wf:
            # 添加自定义头部
            wf.write("全文机翻  \n更多泰百小说见 `https://thaigl.drifting.boats/`\n\n---\n\n")
            
            for fp in chap_files:
                content = Path(fp).read_text(encoding="utf-8").strip()
                if content:
                    wf.write(content + "\n\n")
        
        print(f"✅ 已生成整书 Markdown：{BIG_MD}")
        
    except Exception as e:
        print(f"❌ 合并失败: {e}")

if __name__ == "__main__":
    main()
