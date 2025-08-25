#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF裁切功能测试脚本
演示如何使用PDF裁切工具去除页眉页脚
"""

import sys
from pathlib import Path
from pdf_crop_tool import PDFCropTool

def test_pdf_crop(pdf_path: str):
    """测试PDF裁切功能"""
    if not Path(pdf_path).exists():
        print(f"❌ PDF文件不存在: {pdf_path}")
        return
    
    print(f"🔍 开始分析PDF文件: {pdf_path}")
    
    try:
        # 初始化PDF裁切工具
        crop_tool = PDFCropTool(pdf_path)
        
        # 分析页面布局
        print("\n📊 分析页面布局...")
        analysis = crop_tool.analyze_layout()
        
        if analysis:
            print(f"✅ 检测到 {len(analysis)} 个潜在的页眉页脚区域")
            for i, region in enumerate(analysis[:5]):  # 只显示前5个
                print(f"   区域 {i+1}: 位置({region['x0']:.1f}, {region['y0']:.1f}) 大小({region['width']:.1f}x{region['height']:.1f}) 文本: '{region['text'][:50]}...'")
        else:
            print("⚠️  未检测到明显的页眉页脚区域")
        
        # 预览裁切效果
        print("\n✂️  预览裁切效果...")
        preview = crop_tool.preview_crop_analysis()
        if preview:
            print("📋 裁切预览:")
            for page_num, info in preview.items():
                if page_num < 3:  # 只显示前3页
                    print(f"   页面 {page_num + 1}: 原始文本 {info['original_length']} 字符 -> 裁切后 {info['cropped_length']} 字符")
                    if info['removed_text']:
                        print(f"     移除的文本: '{info['removed_text'][:100]}...'")
        
        # 手动裁切示例
        print("\n🔧 手动裁切示例 (上下各50像素)...")
        crop_tool.crop_page(0, top=50, bottom=50)
        
        # 自动裁切示例
        print("\n🤖 自动裁切示例...")
        crop_tool.auto_crop_page(1, top=30, bottom=30)
        
        print("\n✅ PDF裁切功能测试完成")
        
        # 关闭工具
        crop_tool.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python test_pdf_crop.py <pdf_file_path>")
        print("示例: python test_pdf_crop.py sample.pdf")
        return
    
    pdf_path = sys.argv[1]
    test_pdf_crop(pdf_path)

if __name__ == "__main__":
    main()