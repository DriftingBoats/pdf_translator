#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF裁切命令行工具
提供交互式命令行界面来调整PDF裁切参数
"""

import fitz  # PyMuPDF
import json
from pathlib import Path
from pdf_crop_tool import PDFCropTool
import sys

class PDFCropCLI:
    """PDF裁切命令行工具"""
    
    def __init__(self):
        self.pdf_path = None
        self.crop_tool = None
        self.current_page = 0
        self.total_pages = 0
        
        # 裁切参数
        self.margins = {
            'top': 0,
            'bottom': 0,
            'left': 0,
            'right': 0
        }
    
    def load_pdf(self, pdf_path):
        """加载PDF文件"""
        try:
            self.pdf_path = Path(pdf_path)
            if not self.pdf_path.exists():
                print(f"错误：文件 {pdf_path} 不存在")
                return False
            
            self.crop_tool = PDFCropTool(str(self.pdf_path))
            doc = fitz.open(str(self.pdf_path))
            self.total_pages = len(doc)
            doc.close()
            
            print(f"✅ 成功加载PDF: {self.pdf_path.name}")
            print(f"📄 总页数: {self.total_pages}")
            return True
            
        except Exception as e:
            print(f"❌ 加载PDF失败: {e}")
            return False
    
    def analyze_page(self, page_num=0):
        """分析页面布局"""
        if not self.crop_tool:
            print("❌ 请先加载PDF文件")
            return
        
        try:
            analysis = self.crop_tool.analyze_page_layout(page_num)
            
            print(f"\n📊 页面 {page_num + 1} 布局分析:")
            print(f"📐 页面尺寸: {analysis['page_width']:.1f} x {analysis['page_height']:.1f}")
            print(f"📝 文本块数量: {len(analysis['text_blocks'])}")
            
            if analysis['potential_header']:
                header = analysis['potential_header']
                print(f"📋 检测到页眉: y={header['y0']:.1f}-{header['y1']:.1f}, 内容='{header['text'][:50]}...'")
            
            if analysis['potential_footer']:
                footer = analysis['potential_footer']
                print(f"📋 检测到页脚: y={footer['y0']:.1f}-{footer['y1']:.1f}, 内容='{footer['text'][:50]}...'")
            
            if analysis['suggested_crop']:
                crop = analysis['suggested_crop']
                print(f"\n💡 建议裁切参数:")
                print(f"   顶部: {crop['top']:.1f}px")
                print(f"   底部: {crop['bottom']:.1f}px")
                print(f"   左侧: {crop['left']:.1f}px")
                print(f"   右侧: {crop['right']:.1f}px")
                
                # 询问是否应用建议
                apply = input("\n🤔 是否应用建议的裁切参数? (y/n): ").lower().strip()
                if apply in ['y', 'yes', '是']:
                    self.margins.update(crop)
                    print("✅ 已应用建议的裁切参数")
            
        except Exception as e:
            print(f"❌ 分析页面失败: {e}")
    
    def show_current_settings(self):
        """显示当前设置"""
        print(f"\n⚙️  当前裁切设置:")
        print(f"   顶部边距: {self.margins['top']}px")
        print(f"   底部边距: {self.margins['bottom']}px")
        print(f"   左侧边距: {self.margins['left']}px")
        print(f"   右侧边距: {self.margins['right']}px")
        
        if self.crop_tool:
            print(f"\n📄 当前PDF: {self.pdf_path.name}")
            print(f"📊 总页数: {self.total_pages}")
    
    def adjust_margins(self):
        """交互式调整边距"""
        print("\n🎛️  调整裁切边距 (输入数字，回车确认，直接回车跳过):")
        
        for key, name in [('top', '顶部'), ('bottom', '底部'), ('left', '左侧'), ('right', '右侧')]:
            current = self.margins[key]
            try:
                value = input(f"   {name}边距 (当前: {current}px): ").strip()
                if value:
                    self.margins[key] = float(value)
                    print(f"   ✅ {name}边距设置为 {self.margins[key]}px")
            except ValueError:
                print(f"   ❌ 无效输入，保持原值 {current}px")
    
    def preview_crop(self):
        """预览裁切效果"""
        if not self.crop_tool:
            print("❌ 请先加载PDF文件")
            return
        
        print(f"\n🔍 裁切预览:")
        print(f"   将从PDF的每一页裁切掉:")
        print(f"   • 顶部 {self.margins['top']}px")
        print(f"   • 底部 {self.margins['bottom']}px")
        print(f"   • 左侧 {self.margins['left']}px")
        print(f"   • 右侧 {self.margins['right']}px")
        
        # 计算裁切后的页面尺寸
        try:
            doc = fitz.open(str(self.pdf_path))
            page = doc[0]
            rect = page.rect
            
            new_width = rect.width - self.margins['left'] - self.margins['right']
            new_height = rect.height - self.margins['top'] - self.margins['bottom']
            
            print(f"\n📐 裁切后页面尺寸:")
            print(f"   原始: {rect.width:.1f} x {rect.height:.1f}")
            print(f"   裁切后: {new_width:.1f} x {new_height:.1f}")
            
            if new_width <= 0 or new_height <= 0:
                print("⚠️  警告: 裁切参数过大，可能导致内容丢失！")
            
            doc.close()
            
        except Exception as e:
            print(f"❌ 预览失败: {e}")
    
    def apply_crop(self):
        """应用裁切"""
        if not self.crop_tool:
            print("❌ 请先加载PDF文件")
            return
        
        try:
            output_path = self.pdf_path.parent / f"{self.pdf_path.stem}_cropped.pdf"
            
            print(f"\n🔄 正在应用裁切...")
            self.crop_tool.crop_pages(
                output_path=str(output_path),
                **self.margins
            )
            
            print(f"✅ 裁切完成！")
            print(f"📁 输出文件: {output_path}")
            
        except Exception as e:
            print(f"❌ 裁切失败: {e}")
    
    def save_config(self, config_path=None):
        """保存配置"""
        if not config_path:
            config_path = input("💾 输入配置文件路径 (默认: crop_config.json): ").strip()
            if not config_path:
                config_path = "crop_config.json"
        
        try:
            config = {
                "pdf_crop": {
                    "enable": True,
                    "margins": self.margins
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 配置已保存到: {config_path}")
            
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def load_config(self, config_path=None):
        """加载配置"""
        if not config_path:
            config_path = input("📂 输入配置文件路径: ").strip()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if 'pdf_crop' in config and 'margins' in config['pdf_crop']:
                self.margins.update(config['pdf_crop']['margins'])
                print(f"✅ 配置已加载: {config_path}")
                self.show_current_settings()
            else:
                print("❌ 配置文件格式不正确")
                
        except FileNotFoundError:
            print(f"❌ 配置文件不存在: {config_path}")
        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
    
    def show_help(self):
        """显示帮助信息"""
        print("\n📖 PDF裁切工具帮助:")
        print("   1. load <pdf_path>     - 加载PDF文件")
        print("   2. analyze [page_num]  - 分析页面布局 (默认第1页)")
        print("   3. adjust              - 交互式调整边距")
        print("   4. show                - 显示当前设置")
        print("   5. preview             - 预览裁切效果")
        print("   6. apply               - 应用裁切并生成新PDF")
        print("   7. save [config_path]  - 保存配置")
        print("   8. load_config [path]  - 加载配置")
        print("   9. help                - 显示此帮助")
        print("   10. quit               - 退出程序")
    
    def run(self):
        """运行交互式命令行界面"""
        print("🎯 PDF裁切命令行工具")
        print("输入 'help' 查看可用命令")
        
        while True:
            try:
                command = input("\n> ").strip().split()
                if not command:
                    continue
                
                cmd = command[0].lower()
                
                if cmd in ['quit', 'exit', 'q']:
                    print("👋 再见！")
                    break
                
                elif cmd == 'help':
                    self.show_help()
                
                elif cmd == 'load':
                    if len(command) > 1:
                        self.load_pdf(' '.join(command[1:]))
                    else:
                        pdf_path = input("📁 输入PDF文件路径: ").strip()
                        if pdf_path:
                            self.load_pdf(pdf_path)
                
                elif cmd == 'analyze':
                    if not self.crop_tool:
                        print("❌ 请先加载PDF文件")
                        continue
                    
                    page_num = 0
                    if len(command) > 1:
                        try:
                            page_num = int(command[1]) - 1  # 转换为0索引
                            # 验证页面范围
                            if page_num < 0 or page_num >= self.crop_tool.doc.page_count:
                                print(f"❌ 无效的页面编号: {command[1]} (PDF共有 {self.crop_tool.doc.page_count} 页)")
                                continue
                        except ValueError:
                            print("❌ 无效的页码")
                            continue
                    self.analyze_page(page_num)
                
                elif cmd == 'adjust':
                    self.adjust_margins()
                
                elif cmd == 'show':
                    self.show_current_settings()
                
                elif cmd == 'preview':
                    self.preview_crop()
                
                elif cmd == 'apply':
                    self.apply_crop()
                
                elif cmd == 'save':
                    config_path = ' '.join(command[1:]) if len(command) > 1 else None
                    self.save_config(config_path)
                
                elif cmd == 'load_config':
                    config_path = ' '.join(command[1:]) if len(command) > 1 else None
                    self.load_config(config_path)
                
                else:
                    print(f"❌ 未知命令: {cmd}")
                    print("输入 'help' 查看可用命令")
            
            except KeyboardInterrupt:
                print("\n👋 再见！")
                break
            except Exception as e:
                print(f"❌ 执行命令时出错: {e}")

def main():
    """主函数"""
    cli = PDFCropCLI()
    
    # 如果提供了命令行参数，直接加载PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if cli.load_pdf(pdf_path):
            cli.analyze_page(0)  # 自动分析第一页
    
    cli.run()

if __name__ == "__main__":
    main()