#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PyMuPDF的PDF文本提取功能
验证段落处理是否有改善
"""

import fitz
from pathlib import Path

def test_pymupdf_extraction(pdf_path: str):
    """测试PyMuPDF的文本提取功能"""
    if not Path(pdf_path).exists():
        print(f"❌ PDF文件不存在: {pdf_path}")
        return
    
    print(f"🔍 开始测试PyMuPDF提取: {pdf_path}")
    
    try:
        # 打开PDF文档
        doc = fitz.open(pdf_path)
        print(f"📄 PDF总页数: {doc.page_count}")
        
        # 提取前3页作为示例
        for page_num in range(min(5, doc.page_count)):
            page = doc[page_num]
            print(f"\n=== 第 {page_num + 1} 页 ===")
            
            # 使用blocks模式提取文本
            blocks = page.get_text("blocks", sort=True)
            page_text = ""
            
            print(f"文本块数量: {len(blocks)}")
            
            for i, block in enumerate(blocks):
                if len(block) >= 5 and block[4]:  # 文本块
                    block_text = block[4].strip()
                    if block_text:
                        print(f"\n--- 文本块 {i+1} ---")
                        print(repr(block_text[:200]))  # 显示前200个字符
                        page_text += block_text + "\n\n"
            
            print(f"\n页面文本长度: {len(page_text)} 字符")
            print(f"页面文本预览:\n{page_text[:500]}...")
        
        doc.close()
        print("\n✅ PyMuPDF测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    # 如果有PDF文件，可以在这里指定路径进行测试
    test_pdf = input("请输入PDF文件路径 (或按回车跳过): ").strip()
    if test_pdf:
        test_pymupdf_extraction(test_pdf)
    else:
        print("跳过测试，请手动指定PDF文件路径")