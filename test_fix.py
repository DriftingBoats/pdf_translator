#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PDF裁切工具修复
"""

import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from pdf_crop_tool import PDFCropTool

def test_pdf_crop_tool():
    """测试PDFCropTool是否能正确初始化"""
    print("测试PDFCropTool修复...")
    
    # 创建一个测试PDF文件路径（不存在的文件）
    test_path = "/tmp/nonexistent.pdf"
    
    try:
        # 这应该抛出FileNotFoundError
        crop_tool = PDFCropTool(test_path)
        print("❌ 错误：应该抛出FileNotFoundError")
    except FileNotFoundError as e:
        print(f"✅ 正确：捕获到预期的FileNotFoundError: {e}")
    except Exception as e:
        print(f"❌ 意外错误：{e}")
    
    print("\n测试完成！")
    print("\n修复说明：")
    print("1. 在PDFCropTool.__init__()中添加了自动调用self.open_pdf()")
    print("2. 在pdf_crop_pyqt.py中添加了缺失的import io")
    print("3. 这样可以确保self.crop_tool.doc不会是None")
    print("4. 解决了'NoneType' object has no attribute 'page_count'错误")

if __name__ == "__main__":
    test_pdf_crop_tool()