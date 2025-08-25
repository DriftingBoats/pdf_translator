#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF裁切工具 - 去除页眉页脚
使用PyMuPDF实现PDF页面裁切功能，可以去除页眉页脚区域
"""

import fitz  # PyMuPDF
import json
import logging
from pathlib import Path
from typing import Tuple, Optional

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PDFCropTool:
    """PDF裁切工具类"""
    
    def __init__(self, pdf_path: str):
        """初始化PDF裁切工具
        
        Args:
            pdf_path: PDF文件路径
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        self.doc = None
        self.original_page_size = None
        
        # 自动打开PDF文件
        self.open_pdf()
    
    def open_pdf(self):
        """打开PDF文档"""
        try:
            self.doc = fitz.open(str(self.pdf_path))
            if len(self.doc) > 0:
                # 获取第一页的尺寸作为参考
                first_page = self.doc[0]
                self.original_page_size = first_page.rect
                logging.info(f"PDF已打开: {self.pdf_path.name}")
                logging.info(f"总页数: {len(self.doc)}")
                logging.info(f"页面尺寸: {self.original_page_size}")
            else:
                raise ValueError("PDF文档为空")
        except Exception as e:
            raise RuntimeError(f"打开PDF失败: {e}")
    
    def close_pdf(self):
        """关闭PDF文档"""
        if self.doc:
            self.doc.close()
            self.doc = None
    
    def analyze_page_layout(self, page_num: int = 0) -> dict:
        """分析页面布局，识别可能的页眉页脚区域
        
        Args:
            page_num: 页面编号（从0开始）
            
        Returns:
            包含页面布局分析结果的字典
        """
        if not self.doc or page_num >= len(self.doc):
            raise ValueError(f"无效的页面编号: {page_num}")
        
        page = self.doc[page_num]
        page_rect = page.rect
        
        # 获取文本块
        blocks = page.get_text("blocks")
        
        # 分析文本块位置
        text_blocks = []
        for block in blocks:
            if len(block) >= 5 and block[4].strip():  # 有文本内容的块
                x0, y0, x1, y1 = block[:4]
                text = block[4].strip()
                text_blocks.append({
                    'rect': (x0, y0, x1, y1),
                    'text': text,
                    'y_center': (y0 + y1) / 2,
                    'height': y1 - y0
                })
        
        # 按Y坐标排序
        text_blocks.sort(key=lambda x: x['y_center'])
        
        # 分析可能的页眉页脚
        page_height = page_rect.height
        header_threshold = page_height * 0.15  # 页面顶部15%
        footer_threshold = page_height * 0.85  # 页面底部15%
        
        potential_headers = []
        potential_footers = []
        main_content = []
        
        for block in text_blocks:
            y_center = block['y_center']
            if y_center < header_threshold:
                potential_headers.append(block)
            elif y_center > footer_threshold:
                potential_footers.append(block)
            else:
                main_content.append(block)
        
        # 计算建议的裁切区域
        if main_content:
            # 基于主要内容确定裁切区域
            content_top = min(block['rect'][1] for block in main_content)
            content_bottom = max(block['rect'][3] for block in main_content)
            
            # 添加一些边距
            margin = 20  # 20像素边距
            crop_top = max(0, content_top - margin)
            crop_bottom = min(page_height, content_bottom + margin)
        else:
            # 如果没有主要内容，使用默认裁切
            crop_top = header_threshold
            crop_bottom = footer_threshold
        
        return {
            'page_size': (page_rect.width, page_rect.height),
            'potential_headers': potential_headers,
            'potential_footers': potential_footers,
            'main_content_blocks': len(main_content),
            'suggested_crop': {
                'top': crop_top,
                'bottom': crop_bottom,
                'left': 0,
                'right': page_rect.width
            }
        }
    
    def crop_pages(self, 
                   top_margin: float = 0, 
                   bottom_margin: float = 0, 
                   left_margin: float = 0, 
                   right_margin: float = 0,
                   output_path: Optional[str] = None) -> str:
        """裁切PDF页面
        
        Args:
            top_margin: 顶部裁切边距（像素）
            bottom_margin: 底部裁切边距（像素）
            left_margin: 左侧裁切边距（像素）
            right_margin: 右侧裁切边距（像素）
            output_path: 输出文件路径，如果为None则自动生成
            
        Returns:
            输出文件路径
        """
        if not self.doc:
            raise RuntimeError("PDF文档未打开")
        
        # 生成输出文件路径
        if output_path is None:
            output_path = self.pdf_path.parent / f"{self.pdf_path.stem}_cropped.pdf"
        else:
            output_path = Path(output_path)
        
        logging.info(f"开始裁切PDF: {self.pdf_path.name}")
        logging.info(f"裁切边距 - 上:{top_margin}, 下:{bottom_margin}, 左:{left_margin}, 右:{right_margin}")
        
        # 创建新的PDF文档
        cropped_doc = fitz.open()
        
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            page_rect = page.rect
            
            # 计算裁切矩形
            crop_rect = fitz.Rect(
                left_margin,
                top_margin,
                page_rect.width - right_margin,
                page_rect.height - bottom_margin
            )
            
            # 验证裁切矩形的有效性
            if crop_rect.width <= 0 or crop_rect.height <= 0:
                logging.warning(f"页面 {page_num + 1} 的裁切矩形无效，跳过裁切")
                crop_rect = page_rect
            
            # 设置页面的裁切框
            page.set_cropbox(crop_rect)
            
            # 将裁切后的页面插入到新文档
            cropped_doc.insert_pdf(self.doc, from_page=page_num, to_page=page_num)
        
        # 保存裁切后的PDF
        cropped_doc.save(str(output_path))
        cropped_doc.close()
        
        logging.info(f"PDF裁切完成: {output_path}")
        return str(output_path)
    
    def auto_crop_headers_footers(self, output_path: Optional[str] = None) -> str:
        """自动检测并裁切页眉页脚
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        if not self.doc:
            raise RuntimeError("PDF文档未打开")
        
        # 分析第一页的布局
        layout_analysis = self.analyze_page_layout(0)
        suggested_crop = layout_analysis['suggested_crop']
        
        logging.info("自动检测到的裁切建议:")
        logging.info(f"  顶部裁切: {suggested_crop['top']:.1f}px")
        logging.info(f"  底部裁切: {layout_analysis['page_size'][1] - suggested_crop['bottom']:.1f}px")
        logging.info(f"  检测到 {len(layout_analysis['potential_headers'])} 个可能的页眉")
        logging.info(f"  检测到 {len(layout_analysis['potential_footers'])} 个可能的页脚")
        
        # 执行裁切
        return self.crop_pages(
            top_margin=suggested_crop['top'],
            bottom_margin=layout_analysis['page_size'][1] - suggested_crop['bottom'],
            left_margin=suggested_crop['left'],
            right_margin=layout_analysis['page_size'][0] - suggested_crop['right'],
            output_path=output_path
        )
    
    def preview_crop_analysis(self, page_num: int = 0) -> None:
        """预览裁切分析结果
        
        Args:
            page_num: 要分析的页面编号
        """
        if not self.doc:
            raise RuntimeError("PDF文档未打开")
        
        analysis = self.analyze_page_layout(page_num)
        
        print(f"\n=== 页面 {page_num + 1} 布局分析 ===")
        print(f"页面尺寸: {analysis['page_size'][0]:.1f} x {analysis['page_size'][1]:.1f}")
        print(f"主要内容块数量: {analysis['main_content_blocks']}")
        
        print(f"\n可能的页眉 ({len(analysis['potential_headers'])} 个):")
        for i, header in enumerate(analysis['potential_headers']):
            print(f"  {i+1}. Y位置: {header['y_center']:.1f}, 文本: {header['text'][:50]}...")
        
        print(f"\n可能的页脚 ({len(analysis['potential_footers'])} 个):")
        for i, footer in enumerate(analysis['potential_footers']):
            print(f"  {i+1}. Y位置: {footer['y_center']:.1f}, 文本: {footer['text'][:50]}...")
        
        crop = analysis['suggested_crop']
        print(f"\n建议的裁切区域:")
        print(f"  顶部边距: {crop['top']:.1f}px")
        print(f"  底部边距: {analysis['page_size'][1] - crop['bottom']:.1f}px")
        print(f"  左侧边距: {crop['left']:.1f}px")
        print(f"  右侧边距: {analysis['page_size'][0] - crop['right']:.1f}px")

def main():
    """主函数 - 命令行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PDF裁切工具 - 去除页眉页脚')
    parser.add_argument('pdf_path', help='PDF文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--auto', '-a', action='store_true', help='自动检测并裁切页眉页脚')
    parser.add_argument('--preview', '-p', action='store_true', help='预览裁切分析结果')
    parser.add_argument('--top', type=float, default=0, help='顶部裁切边距（像素）')
    parser.add_argument('--bottom', type=float, default=0, help='底部裁切边距（像素）')
    parser.add_argument('--left', type=float, default=0, help='左侧裁切边距（像素）')
    parser.add_argument('--right', type=float, default=0, help='右侧裁切边距（像素）')
    
    args = parser.parse_args()
    
    try:
        # 创建裁切工具
        crop_tool = PDFCropTool(args.pdf_path)
        crop_tool.open_pdf()
        
        if args.preview:
            # 预览分析结果
            crop_tool.preview_crop_analysis()
        elif args.auto:
            # 自动裁切
            output_path = crop_tool.auto_crop_headers_footers(args.output)
            print(f"\n✅ 自动裁切完成: {output_path}")
        else:
            # 手动裁切
            output_path = crop_tool.crop_pages(
                top_margin=args.top,
                bottom_margin=args.bottom,
                left_margin=args.left,
                right_margin=args.right,
                output_path=args.output
            )
            print(f"\n✅ 手动裁切完成: {output_path}")
        
        crop_tool.close_pdf()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())