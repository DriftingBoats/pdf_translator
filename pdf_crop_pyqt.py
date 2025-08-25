#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF裁切可视化工具 - PyQt6版本

基于PyQt6开发的现代化PDF裁切参数可视化调整工具
提供直观的图形界面，支持实时预览、智能分析、参数调整等功能

作者: AI Assistant
版本: 1.0.0
依赖: PyQt6, PyMuPDF, Pillow
"""

import sys
import os
import json
import io
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QSlider, QSpinBox, QPushButton, QFileDialog, QScrollArea,
        QGroupBox, QGridLayout, QTextEdit, QSplitter, QFrame, QMessageBox,
        QProgressBar, QComboBox, QCheckBox
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QPixmap, QFont, QPalette, QColor, QIcon
except ImportError:
    print("❌ 错误: 未安装PyQt6")
    print("请运行: pip install PyQt6")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ 错误: 未安装PyMuPDF")
    print("请运行: pip install PyMuPDF")
    sys.exit(1)

try:
    from PIL import Image, ImageQt
except ImportError:
    print("❌ 错误: 未安装Pillow")
    print("请运行: pip install Pillow")
    sys.exit(1)

from pdf_crop_tool import PDFCropTool


class PDFAnalysisThread(QThread):
    """PDF分析线程"""
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, crop_tool, page_num):
        super().__init__()
        self.crop_tool = crop_tool
        self.page_num = page_num
    
    def run(self):
        try:
            analysis = self.crop_tool.analyze_page_layout(self.page_num)
            self.analysis_complete.emit(analysis)
        except Exception as e:
            self.error_occurred.emit(str(e))


class PDFCropPyQt(QMainWindow):
    """PyQt6版本的PDF裁切可视化工具"""
    
    def __init__(self):
        super().__init__()
        self.crop_tool: Optional[PDFCropTool] = None
        self.current_page = 0
        self.total_pages = 0
        self.current_pixmap: Optional[QPixmap] = None
        self.margins = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}
        self.analysis_thread: Optional[PDFAnalysisThread] = None
        
        self.init_ui()
        self.setup_styles()
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("PDF裁切可视化工具 - PyQt6版本")
        self.setGeometry(100, 100, 1400, 900)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧控制面板
        self.create_control_panel(splitter)
        
        # 右侧预览区域
        self.create_preview_area(splitter)
        
        # 设置分割器比例
        splitter.setSizes([400, 1000])
        
        # 状态栏
        self.statusBar().showMessage("就绪 - 请选择PDF文件")
        
    def create_control_panel(self, parent):
        """创建左侧控制面板"""
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # 文件操作组
        file_group = QGroupBox("文件操作")
        file_layout = QVBoxLayout(file_group)
        
        self.open_btn = QPushButton("📁 选择PDF文件")
        self.open_btn.clicked.connect(self.open_pdf)
        file_layout.addWidget(self.open_btn)
        
        self.file_info = QLabel("未选择文件")
        self.file_info.setWordWrap(True)
        file_layout.addWidget(self.file_info)
        
        control_layout.addWidget(file_group)
        
        # 页面导航组
        nav_group = QGroupBox("页面导航")
        nav_layout = QGridLayout(nav_group)
        
        self.prev_btn = QPushButton("⬅️ 上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn, 0, 0)
        
        self.next_btn = QPushButton("➡️ 下一页")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn, 0, 1)
        
        self.page_info = QLabel("页面: 0 / 0")
        self.page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.page_info, 1, 0, 1, 2)
        
        control_layout.addWidget(nav_group)
        
        # 智能分析组
        analysis_group = QGroupBox("智能分析")
        analysis_layout = QVBoxLayout(analysis_group)
        
        self.analyze_btn = QPushButton("🔍 分析当前页面")
        self.analyze_btn.clicked.connect(self.analyze_current_page)
        self.analyze_btn.setEnabled(False)
        analysis_layout.addWidget(self.analyze_btn)
        
        self.auto_apply_cb = QCheckBox("自动应用分析结果")
        self.auto_apply_cb.setChecked(True)
        analysis_layout.addWidget(self.auto_apply_cb)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        analysis_layout.addWidget(self.progress_bar)
        
        control_layout.addWidget(analysis_group)
        
        # 裁切参数组
        self.create_margin_controls(control_layout)
        
        # 预设配置组
        self.create_preset_controls(control_layout)
        
        # 操作按钮组
        self.create_action_buttons(control_layout)
        
        # 分析结果显示
        self.create_analysis_display(control_layout)
        
        control_layout.addStretch()
        parent.addWidget(control_widget)
        
    def create_margin_controls(self, parent_layout):
        """创建边距控制组件"""
        margin_group = QGroupBox("裁切参数 (像素)")
        margin_layout = QGridLayout(margin_group)
        
        # 创建滑块和输入框
        self.margin_controls = {}
        margins = [('top', '顶部'), ('bottom', '底部'), ('left', '左侧'), ('right', '右侧')]
        
        for i, (key, label) in enumerate(margins):
            # 标签
            margin_layout.addWidget(QLabel(f"{label}:"), i, 0)
            
            # 滑块
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(0)
            slider.valueChanged.connect(lambda v, k=key: self.update_margin(k, v))
            margin_layout.addWidget(slider, i, 1)
            
            # 输入框
            spinbox = QSpinBox()
            spinbox.setRange(0, 500)
            spinbox.setValue(0)
            spinbox.valueChanged.connect(lambda v, k=key: self.update_margin_from_spinbox(k, v))
            margin_layout.addWidget(spinbox, i, 2)
            
            self.margin_controls[key] = {'slider': slider, 'spinbox': spinbox}
        
        # 重置按钮
        reset_btn = QPushButton("🔄 重置参数")
        reset_btn.clicked.connect(self.reset_margins)
        margin_layout.addWidget(reset_btn, len(margins), 0, 1, 3)
        
        parent_layout.addWidget(margin_group)
        
    def create_preset_controls(self, parent_layout):
        """创建预设配置控制组件"""
        preset_group = QGroupBox("预设配置")
        preset_layout = QVBoxLayout(preset_group)
        
        # 预设选择
        preset_layout.addWidget(QLabel("选择预设:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "无预设",
            "标准文档 (上下各20px)",
            "学术论文 (上下各30px)",
            "杂志文章 (四周各15px)",
            "扫描文档 (四周各25px)"
        ])
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        preset_layout.addWidget(self.preset_combo)
        
        # 配置文件操作
        config_layout = QHBoxLayout()
        
        save_config_btn = QPushButton("💾 保存配置")
        save_config_btn.clicked.connect(self.save_config)
        config_layout.addWidget(save_config_btn)
        
        load_config_btn = QPushButton("📂 加载配置")
        load_config_btn.clicked.connect(self.load_config)
        config_layout.addWidget(load_config_btn)
        
        preset_layout.addLayout(config_layout)
        parent_layout.addWidget(preset_group)
        
    def create_action_buttons(self, parent_layout):
        """创建操作按钮组件"""
        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)
        
        self.preview_btn = QPushButton("👁️ 预览裁切效果")
        self.preview_btn.clicked.connect(self.preview_crop)
        self.preview_btn.setEnabled(False)
        action_layout.addWidget(self.preview_btn)
        
        self.apply_btn = QPushButton("✅ 应用并保存")
        self.apply_btn.clicked.connect(self.apply_crop)
        self.apply_btn.setEnabled(False)
        action_layout.addWidget(self.apply_btn)
        
        parent_layout.addWidget(action_group)
        
    def create_analysis_display(self, parent_layout):
        """创建分析结果显示组件"""
        analysis_group = QGroupBox("分析结果")
        analysis_layout = QVBoxLayout(analysis_group)
        
        self.analysis_text = QTextEdit()
        self.analysis_text.setMaximumHeight(150)
        self.analysis_text.setPlainText("暂无分析结果")
        analysis_layout.addWidget(self.analysis_text)
        
        parent_layout.addWidget(analysis_group)
        
    def create_preview_area(self, parent):
        """创建右侧预览区域"""
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        # 预览标题
        title_label = QLabel("PDF预览")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        preview_layout.addWidget(title_label)
        
        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # PDF显示标签
        self.pdf_label = QLabel()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pdf_label.setMinimumSize(600, 800)
        self.pdf_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #cccccc;
                border-radius: 10px;
                background-color: #f9f9f9;
                color: #666666;
                font-size: 16px;
            }
        """)
        self.pdf_label.setText("请选择PDF文件进行预览")
        
        self.scroll_area.setWidget(self.pdf_label)
        preview_layout.addWidget(self.scroll_area)
        
        parent.addWidget(preview_widget)
        
    def setup_styles(self):
        """设置界面样式"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
        """)
        
    def open_pdf(self):
        """打开PDF文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择PDF文件", "", "PDF文件 (*.pdf)"
        )
        
        if file_path:
            try:
                self.crop_tool = PDFCropTool(file_path)
                self.total_pages = self.crop_tool.doc.page_count
                self.current_page = 0
                
                # 更新界面
                self.file_info.setText(f"文件: {Path(file_path).name}\n页数: {self.total_pages}")
                self.update_page_info()
                self.enable_controls(True)
                self.load_current_page()
                
                self.statusBar().showMessage(f"已加载: {Path(file_path).name}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开PDF文件:\n{str(e)}")
                
    def enable_controls(self, enabled: bool):
        """启用/禁用控件"""
        self.prev_btn.setEnabled(enabled and self.current_page > 0)
        self.next_btn.setEnabled(enabled and self.current_page < self.total_pages - 1)
        self.analyze_btn.setEnabled(enabled)
        self.preview_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        
    def update_page_info(self):
        """更新页面信息"""
        self.page_info.setText(f"页面: {self.current_page + 1} / {self.total_pages}")
        self.enable_controls(True)
        
    def prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page_info()
            self.load_current_page()
            
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_page_info()
            self.load_current_page()
            
    def load_current_page(self):
        """加载当前页面"""
        if not self.crop_tool:
            return
            
        try:
            # 获取页面
            page = self.crop_tool.doc[self.current_page]
            
            # 渲染为图像
            mat = fitz.Matrix(2.0, 2.0)  # 2倍缩放以提高清晰度
            pix = page.get_pixmap(matrix=mat)
            
            # 转换为PIL图像
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # 应用裁切预览
            if any(self.margins.values()):
                pil_image = self.apply_crop_to_image(pil_image)
            
            # 转换为QPixmap
            qt_image = ImageQt.ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qt_image)
            
            # 缩放以适应显示区域
            scaled_pixmap = pixmap.scaled(
                800, 1000, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.pdf_label.setPixmap(scaled_pixmap)
            self.current_pixmap = pixmap
            
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法加载页面: {str(e)}")
            
    def apply_crop_to_image(self, image: Image.Image) -> Image.Image:
        """对图像应用裁切"""
        width, height = image.size
        
        left = self.margins['left']
        top = self.margins['top']
        right = width - self.margins['right']
        bottom = height - self.margins['bottom']
        
        # 确保裁切区域有效
        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        
        return image.crop((left, top, right, bottom))
        
    def update_margin(self, margin_type: str, value: int):
        """更新边距值"""
        self.margins[margin_type] = value
        
        # 同步滑块和输入框
        control = self.margin_controls[margin_type]
        control['slider'].setValue(value)
        control['spinbox'].setValue(value)
        
        # 实时更新预览
        self.load_current_page()
        
    def update_margin_from_spinbox(self, margin_type: str, value: int):
        """从输入框更新边距值"""
        self.margins[margin_type] = value
        
        # 同步滑块
        control = self.margin_controls[margin_type]
        control['slider'].setValue(value)
        
        # 实时更新预览
        self.load_current_page()
        
    def reset_margins(self):
        """重置所有边距"""
        for margin_type in self.margins:
            self.update_margin(margin_type, 0)
            
    def apply_preset(self, preset_name: str):
        """应用预设配置"""
        presets = {
            "标准文档 (上下各20px)": {'top': 20, 'bottom': 20, 'left': 0, 'right': 0},
            "学术论文 (上下各30px)": {'top': 30, 'bottom': 30, 'left': 0, 'right': 0},
            "杂志文章 (四周各15px)": {'top': 15, 'bottom': 15, 'left': 15, 'right': 15},
            "扫描文档 (四周各25px)": {'top': 25, 'bottom': 25, 'left': 25, 'right': 25}
        }
        
        if preset_name in presets:
            preset_margins = presets[preset_name]
            for margin_type, value in preset_margins.items():
                self.update_margin(margin_type, value)
        elif preset_name == "无预设":
            self.reset_margins()
            
    def analyze_current_page(self):
        """分析当前页面"""
        if not self.crop_tool:
            return
            
        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        
        # 启动分析线程
        self.analysis_thread = PDFAnalysisThread(self.crop_tool, self.current_page)
        self.analysis_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analysis_thread.error_occurred.connect(self.on_analysis_error)
        self.analysis_thread.start()
        
    def on_analysis_complete(self, analysis: Dict[str, Any]):
        """分析完成回调"""
        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 显示分析结果
        result_text = f"页面尺寸: {analysis['page_width']:.1f} x {analysis['page_height']:.1f}\n"
        result_text += f"文本块数量: {len(analysis['text_blocks'])}\n\n"
        
        if analysis['potential_header']:
            header = analysis['potential_header']
            result_text += f"检测到页眉:\n  位置: y={header['y0']:.1f}-{header['y1']:.1f}\n"
            result_text += f"  内容: {header['text'][:50]}...\n\n"
            
        if analysis['potential_footer']:
            footer = analysis['potential_footer']
            result_text += f"检测到页脚:\n  位置: y={footer['y0']:.1f}-{footer['y1']:.1f}\n"
            result_text += f"  内容: {footer['text'][:50]}...\n\n"
            
        if analysis['suggested_crop']:
            crop = analysis['suggested_crop']
            result_text += f"建议裁切参数:\n"
            result_text += f"  顶部: {crop['top']:.1f}px\n"
            result_text += f"  底部: {crop['bottom']:.1f}px\n"
            result_text += f"  左侧: {crop['left']:.1f}px\n"
            result_text += f"  右侧: {crop['right']:.1f}px"
            
            # 自动应用建议
            if self.auto_apply_cb.isChecked():
                for margin_type, value in crop.items():
                    self.update_margin(margin_type, int(value))
                    
        self.analysis_text.setPlainText(result_text)
        
    def on_analysis_error(self, error_msg: str):
        """分析错误回调"""
        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "分析错误", f"页面分析失败:\n{error_msg}")
        
    def preview_crop(self):
        """预览裁切效果"""
        if not self.crop_tool:
            return
            
        # 重新加载当前页面以显示裁切效果
        self.load_current_page()
        self.statusBar().showMessage("已更新预览")
        
    def apply_crop(self):
        """应用裁切并保存"""
        if not self.crop_tool:
            return
            
        try:
            # 应用裁切
            output_path = self.crop_tool.apply_crop(
                self.margins['top'],
                self.margins['bottom'], 
                self.margins['left'],
                self.margins['right']
            )
            
            QMessageBox.information(
                self, "成功", 
                f"裁切完成！\n输出文件: {output_path}"
            )
            
            self.statusBar().showMessage(f"裁切完成: {Path(output_path).name}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"应用裁切失败:\n{str(e)}")
            
    def save_config(self):
        """保存配置"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件", "crop_config.json", "JSON文件 (*.json)"
        )
        
        if file_path:
            try:
                config = {
                    'pdf_crop': self.margins,
                    'description': '使用PyQt工具生成的PDF裁切配置'
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                    
                QMessageBox.information(self, "成功", f"配置已保存到: {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存配置失败:\n{str(e)}")
                
    def load_config(self):
        """加载配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载配置文件", "", "JSON文件 (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                if 'pdf_crop' in config:
                    crop_config = config['pdf_crop']
                    for margin_type, value in crop_config.items():
                        if margin_type in self.margins:
                            self.update_margin(margin_type, int(value))
                            
                    QMessageBox.information(self, "成功", "配置加载完成")
                else:
                    QMessageBox.warning(self, "警告", "配置文件格式不正确")
                    
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载配置失败:\n{str(e)}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("PDF裁切可视化工具")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("PDF Translator")
    
    # 创建主窗口
    window = PDFCropPyQt()
    window.show()
    
    # 如果提供了命令行参数，自动加载PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            window.crop_tool = PDFCropTool(pdf_path)
            window.total_pages = window.crop_tool.doc.page_count
            window.current_page = 0
            window.file_info.setText(f"文件: {Path(pdf_path).name}\n页数: {window.total_pages}")
            window.update_page_info()
            window.enable_controls(True)
            window.load_current_page()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    # 添加缺失的导入
    import io
    main()