#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节翻译代理（中文版）
Usage:
    python chapter_translation_agent_cn.py            # 默认读取 config.json
"""
import json, re, textwrap, time, hashlib, random
from pathlib import Path
from typing import List
import requests, yaml
from tqdm import tqdm
from PyPDF2 import PdfReader

# ---------- 路径 & 配置 ----------
ROOT = Path(__file__).resolve().parent
CONFIG = json.load(open(ROOT / "config.json", encoding="utf-8"))

API_URL      = CONFIG["api"]["API_URL"]
API_KEY      = CONFIG["api"]["API_KEY"]
LLM_MODEL    = CONFIG["api"]["LLM_MODEL"]
TEMPERATURE  = CONFIG["api"].get("temperature", 0.2)

PDF_PATH     = Path(CONFIG["paths"]["pdf"])
OUT_DIR      = Path(CONFIG["paths"]["output_dir"])
BIG_MD_NAME  = CONFIG["paths"]["big_md_name"]

CHAP_MAP     = {k: tuple(v) for k, v in CONFIG["chapters"].items()}

# ---------- glossary ----------
GLOSS_FILE = ROOT / "glossary.yaml"
def load_glossary():
    if GLOSS_FILE.exists():
        return yaml.safe_load(open(GLOSS_FILE, encoding="utf-8")) or {}
    return {}
def save_glossary(dic):
    yaml.safe_dump(dic, open(GLOSS_FILE, "w", encoding="utf-8"), allow_unicode=True)
glossary = load_glossary()

# ---------- style cache ----------
STYLE_FILE = ROOT / "style_cache.txt"
style_cache = STYLE_FILE.read_text(encoding="utf-8") if STYLE_FILE.exists() else ""

# ---------- LLM 调用 ----------
def call_llm(prompt: str, max_tokens: int = 2048) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
    }
    for _ in range(3):  # 简易重试
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("LLM 调用失败，重试:", e)
            time.sleep(3)
    raise RuntimeError("LLM 调用连续失败")

# ---------- 辅助 ----------
def pdf_extract_pages(reader: PdfReader, start: int, end: int) -> str:
    texts = []
    for i in range(start-1, end):
        texts.append(reader.pages[i].extract_text() or "")
    return "\n".join(texts).strip()

def refresh_style(sample: str):
    global style_cache
    if style_cache:
        return
    print("◎ 首次生成行文风格摘要…")
    prompt = textwrap.dedent(f"""\
        You are a literary critic. Summarize the narrative voice, tone,
        humour level and sentence rhythm of the following English fiction
        excerpt in **no more than 80 English words**:

        ```text
        {sample[:1500]}
        ```
        Output only the summary.""")
    style_cache = call_llm(prompt, 256)
    STYLE_FILE.write_text(style_cache, encoding="utf-8")

def build_prompt(src_text: str, chap_no: str) -> str:
    gloss_block = "\n".join(f"{k}\t{v}" for k, v in glossary.items()) or "（空）"
    return textwrap.dedent(f"""\
        你是一名资深文学译者，需将【泰语→英译→中文】的英译本小说精准、流畅地译成现代中文。
        ✦ 请延续下述「原文行文风格摘要」：{style_cache}
        ✦ 段落：严格对应，不增删、不合并。
        ✦ 名称/尊称：若出现在术语表中则 <保留不译>；若未出现，则保持原貌并追加到术语表。
        ✦ 标点：中文全角；英文专名内保留半角。
        ✦ 数字与单位照原文。
        ============ 术语表 ============
        {gloss_block}
        ============ 待翻译正文 ============
        ## {chap_no}

        {src_text}
        """).strip()

def update_glossary_from_translation(tr_text: str):
    m = re.search(r"```glossary(.*?)```", tr_text, re.S | re.I)
    if not m:
        return
    for raw in m.group(1).strip().splitlines():
        if not raw.strip():
            continue
        if '\t' not in raw:
            continue
        src, tgt = map(str.strip, raw.split("\t", 1))
        if glossary.get(src) != tgt:
            glossary[src] = tgt
    save_glossary(glossary)

# ---------- 主流程 ----------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(PDF_PATH))
    # ---- 取样生成风格摘要 ----
    first_chap = list(CHAP_MAP.items())[0]
    sample_text = pdf_extract_pages(reader, *first_chap[1])
    refresh_style(sample_text)

    all_md_paths = []
    for chap_no, (s, e) in CHAP_MAP.items():
        out_file = OUT_DIR / f"{chap_no}.md"
        if out_file.exists():
            print(f"[√] 跳过已存在章节 {chap_no}")
            all_md_paths.append(out_file)
            continue

        print(f"=== 处理章节 {chap_no}  页 {s}-{e} ===")
        src = pdf_extract_pages(reader, s, e)
        prompt = build_prompt(src, chap_no)
        trans = call_llm(prompt)
        update_glossary_from_translation(trans)
        out_file.write_text(trans, encoding="utf-8")
        all_md_paths.append(out_file)

    print("✔︎ 全书翻译完成成")

if __name__ == "__main__":
    main()
