#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF裁切可视化工具
提供图形界面来可视化调整PDF裁切参数
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import json
from pathlib import Path
from pdf_crop_tool import PDFCropTool

class PDFCropVisualizer:
    """PDF裁切可视化工具"""
    
    def __init__(self, root):
        try:
            print("初始化PDF裁切可视化工具...")
            self.root = root
            self.root.title("PDF裁切可视化工具")
            self.root.geometry("1200x800")
            
            # 初始化变量
            self.pdf_path = None
            self.crop_tool = None
            self.current_page = 0
            self.total_pages = 0
            self.page_image = None
            self.canvas_image = None
            self.scale_factor = 1.0
            
            # 裁切参数
            self.top_margin = tk.DoubleVar(value=0)
            self.bottom_margin = tk.DoubleVar(value=0)
            self.left_margin = tk.DoubleVar(value=0)
            self.right_margin = tk.DoubleVar(value=0)
            
            print("创建界面组件...")
            # 创建界面
            self.create_widgets()
            print("界面创建完成")
            
        except Exception as e:
            print(f"初始化时出错: {e}")
            import traceback
            traceback.print_exc()
            raise
        
    def create_widgets(self):
        """创建界面组件"""
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部控制面板
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 文件选择
        ttk.Button(control_frame, text="选择PDF文件", command=self.select_pdf).pack(side=tk.LEFT, padx=(0, 10))
        
        # 页面导航
        nav_frame = ttk.Frame(control_frame)
        nav_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(nav_frame, text="上一页", command=self.prev_page).pack(side=tk.LEFT)
        self.page_label = ttk.Label(nav_frame, text="页面: 0/0")
        self.page_label.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(nav_frame, text="下一页", command=self.next_page).pack(side=tk.LEFT)
        
        # 自动检测按钮
        ttk.Button(control_frame, text="自动检测", command=self.auto_detect).pack(side=tk.LEFT, padx=(10, 0))
        
        # 主内容区域
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：PDF预览
        preview_frame = ttk.LabelFrame(content_frame, text="PDF预览")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 创建画布和滚动条
        canvas_frame = ttk.Frame(preview_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(canvas_frame, bg='white')
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 右侧：参数调整
        params_frame = ttk.LabelFrame(content_frame, text="裁切参数")
        params_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 0))
        params_frame.configure(width=300)
        
        # 参数输入区域
        self.create_parameter_controls(params_frame)
        
        # 底部按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="预览裁切效果", command=self.preview_crop).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="应用裁切", command=self.apply_crop).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="加载配置", command=self.load_config).pack(side=tk.LEFT)
        
    def create_parameter_controls(self, parent):
        """创建参数控制组件"""
        # 参数标签和输入框
        params = [
            ("顶部边距 (px)", self.top_margin),
            ("底部边距 (px)", self.bottom_margin),
            ("左侧边距 (px)", self.left_margin),
            ("右侧边距 (px)", self.right_margin)
        ]
        
        for i, (label, var) in enumerate(params):
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(frame, text=label).pack(anchor=tk.W)
            
            # 创建滑块和输入框
            slider_frame = ttk.Frame(frame)
            slider_frame.pack(fill=tk.X, pady=(5, 0))
            
            slider = ttk.Scale(slider_frame, from_=0, to=200, variable=var, 
                             orient=tk.HORIZONTAL, command=self.on_parameter_change)
            slider.pack(fill=tk.X)
            
            entry = ttk.Entry(slider_frame, textvariable=var, width=10)
            entry.pack(pady=(5, 0))
            entry.bind('<Return>', self.on_parameter_change)
            entry.bind('<FocusOut>', self.on_parameter_change)
        
        # 分隔线
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=20)
        
        # 页面信息
        info_frame = ttk.LabelFrame(parent, text="页面信息")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.info_text = tk.Text(info_frame, height=8, width=30, wrap=tk.WORD)
        self.info_text.pack(padx=5, pady=5)
        
        # 预设按钮
        preset_frame = ttk.LabelFrame(parent, text="预设配置")
        preset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(preset_frame, text="重置", command=self.reset_parameters).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(preset_frame, text="标准页眉页脚", command=self.preset_standard).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(preset_frame, text="学术论文", command=self.preset_academic).pack(fill=tk.X, padx=5, pady=2)
        
    def select_pdf(self):
        """选择PDF文件"""
        file_path = filedialog.askopenfilename(
            title="选择PDF文件",
            filetypes=[("PDF文件", "*.pdf")]
        )
        
        if file_path:
            try:
                self.pdf_path = file_path
                self.crop_tool = PDFCropTool(file_path)
                self.crop_tool.open_pdf()
                
                self.total_pages = len(self.crop_tool.doc)
                self.current_page = 0
                
                self.update_page_display()
                self.update_page_info()
                
                messagebox.showinfo("成功", f"已加载PDF文件\n页数: {self.total_pages}")
                
            except Exception as e:
                messagebox.showerror("错误", f"加载PDF文件失败:\n{e}")
    
    def update_page_display(self):
        """更新页面显示"""
        if not self.crop_tool:
            return
        
        try:
            # 获取页面
            page = self.crop_tool.doc[self.current_page]
            
            # 转换为图像
            mat = fitz.Matrix(2.0, 2.0)  # 2倍缩放以提高清晰度
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            
            # 转换为PIL图像
            import io
            self.page_image = Image.open(io.BytesIO(img_data))
            
            # 计算缩放比例以适应画布
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:  # 确保画布已初始化
                img_width, img_height = self.page_image.size
                scale_x = (canvas_width - 20) / img_width
                scale_y = (canvas_height - 20) / img_height
                self.scale_factor = min(scale_x, scale_y, 1.0)  # 不放大，只缩小
                
                # 缩放图像
                new_width = int(img_width * self.scale_factor)
                new_height = int(img_height * self.scale_factor)
                display_image = self.page_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 转换为tkinter图像
                self.canvas_image = ImageTk.PhotoImage(display_image)
                
                # 清除画布并显示图像
                self.canvas.delete("all")
                self.canvas.create_image(10, 10, anchor=tk.NW, image=self.canvas_image)
                
                # 更新滚动区域
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                
                # 绘制裁切区域
                self.draw_crop_overlay()
            
            # 更新页面标签
            self.page_label.config(text=f"页面: {self.current_page + 1}/{self.total_pages}")
            
        except Exception as e:
            messagebox.showerror("错误", f"显示页面失败:\n{e}")
    
    def draw_crop_overlay(self):
        """绘制裁切区域覆盖层"""
        if not self.page_image or not self.canvas_image:
            return
        
        # 获取图像尺寸
        img_width, img_height = self.page_image.size
        display_width = int(img_width * self.scale_factor)
        display_height = int(img_height * self.scale_factor)
        
        # 计算裁切区域（缩放后的坐标）
        top = int(self.top_margin.get() * self.scale_factor) + 10
        bottom = display_height - int(self.bottom_margin.get() * self.scale_factor) + 10
        left = int(self.left_margin.get() * self.scale_factor) + 10
        right = display_width - int(self.right_margin.get() * self.scale_factor) + 10
        
        # 绘制半透明覆盖层（被裁切的区域）
        # 顶部
        if top > 10:
            self.canvas.create_rectangle(10, 10, display_width + 10, top, 
                                       fill='red', stipple='gray50', outline='red', width=2)
        
        # 底部
        if bottom < display_height + 10:
            self.canvas.create_rectangle(10, bottom, display_width + 10, display_height + 10, 
                                       fill='red', stipple='gray50', outline='red', width=2)
        
        # 左侧
        if left > 10:
            self.canvas.create_rectangle(10, top, left, bottom, 
                                       fill='red', stipple='gray50', outline='red', width=2)
        
        # 右侧
        if right < display_width + 10:
            self.canvas.create_rectangle(right, top, display_width + 10, bottom, 
                                       fill='red', stipple='gray50', outline='red', width=2)
        
        # 绘制保留区域边框
        self.canvas.create_rectangle(left, top, right, bottom, 
                                   outline='green', width=3)
        
        # 添加标签
        self.canvas.create_text(left + 5, top + 5, text="保留区域", 
                              fill='green', font=('Arial', 12, 'bold'), anchor=tk.NW)
    
    def on_parameter_change(self, event=None):
        """参数变化时的回调"""
        # 重新绘制裁切覆盖层
        if self.canvas_image:
            self.update_page_display()
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page_display()
            self.update_page_info()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_page_display()
            self.update_page_info()
    
    def auto_detect(self):
        """自动检测页眉页脚"""
        if not self.crop_tool:
            messagebox.showwarning("警告", "请先选择PDF文件")
            return
        
        try:
            # 分析当前页面
            analysis = self.crop_tool.analyze_page_layout(self.current_page)
            suggested = analysis['suggested_crop']
            page_height = analysis['page_size'][1]
            page_width = analysis['page_size'][0]
            
            # 设置参数
            self.top_margin.set(suggested['top'])
            self.bottom_margin.set(page_height - suggested['bottom'])
            self.left_margin.set(suggested['left'])
            self.right_margin.set(page_width - suggested['right'])
            
            # 更新显示
            self.update_page_display()
            
            messagebox.showinfo("自动检测完成", 
                              f"检测到 {len(analysis['potential_headers'])} 个页眉\n"
                              f"检测到 {len(analysis['potential_footers'])} 个页脚")
            
        except Exception as e:
            messagebox.showerror("错误", f"自动检测失败:\n{e}")
    
    def update_page_info(self):
        """更新页面信息"""
        if not self.crop_tool:
            return
        
        try:
            analysis = self.crop_tool.analyze_page_layout(self.current_page)
            
            info = f"页面尺寸: {analysis['page_size'][0]:.0f} x {analysis['page_size'][1]:.0f}\n"
            info += f"主要内容块: {analysis['main_content_blocks']}\n\n"
            
            info += f"可能的页眉 ({len(analysis['potential_headers'])} 个):\n"
            for i, header in enumerate(analysis['potential_headers'][:3]):
                info += f"  {i+1}. {header['text'][:30]}...\n"
            
            info += f"\n可能的页脚 ({len(analysis['potential_footers'])} 个):\n"
            for i, footer in enumerate(analysis['potential_footers'][:3]):
                info += f"  {i+1}. {footer['text'][:30]}...\n"
            
            self.info_text.delete(1.0, tk.END)
            self.info_text.insert(1.0, info)
            
        except Exception as e:
            self.info_text.delete(1.0, tk.END)
            self.info_text.insert(1.0, f"获取页面信息失败: {e}")
    
    def reset_parameters(self):
        """重置参数"""
        self.top_margin.set(0)
        self.bottom_margin.set(0)
        self.left_margin.set(0)
        self.right_margin.set(0)
        self.update_page_display()
    
    def preset_standard(self):
        """标准页眉页脚预设"""
        self.top_margin.set(50)
        self.bottom_margin.set(50)
        self.left_margin.set(30)
        self.right_margin.set(30)
        self.update_page_display()
    
    def preset_academic(self):
        """学术论文预设"""
        self.top_margin.set(70)
        self.bottom_margin.set(70)
        self.left_margin.set(50)
        self.right_margin.set(50)
        self.update_page_display()
    
    def preview_crop(self):
        """预览裁切效果"""
        if not self.crop_tool:
            messagebox.showwarning("警告", "请先选择PDF文件")
            return
        
        # 当前的可视化已经是预览效果
        messagebox.showinfo("预览", "当前显示即为裁切预览效果\n红色区域将被裁切，绿色边框内为保留区域")
    
    def apply_crop(self):
        """应用裁切"""
        if not self.crop_tool:
            messagebox.showwarning("警告", "请先选择PDF文件")
            return
        
        # 选择输出文件
        output_path = filedialog.asksaveasfilename(
            title="保存裁切后的PDF",
            defaultextension=".pdf",
            filetypes=[("PDF文件", "*.pdf")]
        )
        
        if output_path:
            try:
                result_path = self.crop_tool.crop_pages(
                    top_margin=self.top_margin.get(),
                    bottom_margin=self.bottom_margin.get(),
                    left_margin=self.left_margin.get(),
                    right_margin=self.right_margin.get(),
                    output_path=output_path
                )
                
                messagebox.showinfo("成功", f"PDF裁切完成！\n保存位置: {result_path}")
                
            except Exception as e:
                messagebox.showerror("错误", f"裁切失败:\n{e}")
    
    def save_config(self):
        """保存配置"""
        config = {
            "top_margin": self.top_margin.get(),
            "bottom_margin": self.bottom_margin.get(),
            "left_margin": self.left_margin.get(),
            "right_margin": self.right_margin.get()
        }
        
        file_path = filedialog.asksaveasfilename(
            title="保存裁切配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("成功", "配置已保存")
            except Exception as e:
                messagebox.showerror("错误", f"保存配置失败:\n{e}")
    
    def load_config(self):
        """加载配置"""
        file_path = filedialog.askopenfilename(
            title="加载裁切配置",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.top_margin.set(config.get('top_margin', 0))
                self.bottom_margin.set(config.get('bottom_margin', 0))
                self.left_margin.set(config.get('left_margin', 0))
                self.right_margin.set(config.get('right_margin', 0))
                
                self.update_page_display()
                messagebox.showinfo("成功", "配置已加载")
                
            except Exception as e:
                messagebox.showerror("错误", f"加载配置失败:\n{e}")

def main():
    """主函数"""
    try:
        # 设置环境变量以抑制tkinter警告
        import os
        os.environ['TK_SILENCE_DEPRECATION'] = '1'
        
        root = tk.Tk()
        
        # 确保窗口显示
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(root.attributes, '-topmost', False)
        
        app = PDFCropVisualizer(root)
        
        # 绑定窗口关闭事件
        def on_closing():
            try:
                if app.crop_tool:
                    app.crop_tool.close_pdf()
            except Exception as e:
                print(f"关闭时出错: {e}")
            finally:
                root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # 强制更新界面
        root.update_idletasks()
        root.update()
        
        print("PDF裁切可视化工具已启动")
        print("请点击'选择PDF文件'按钮开始使用")
        
        root.mainloop()
        
    except Exception as e:
        print(f"启动GUI时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()