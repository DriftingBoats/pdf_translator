#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 outputs/book_title/*.md 按文件名顺序合并为 big_md_name
"""
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG  = json.load(open(ROOT / "config.json", encoding="utf-8"))
OUT_DIR = Path(CFG["paths"]["output_dir"])
BIG_MD  = OUT_DIR / CFG["paths"]["big_md_name"]

chap_files = sorted(glob.glob(str(OUT_DIR / "*.md")))
with open(BIG_MD, "w", encoding="utf-8") as wf:
    for fp in chap_files:
        wf.write(Path(fp).read_text(encoding="utf-8").strip() + "\n\n")

print(f"✅ 已生成整书 Markdown：{BIG_MD}")
