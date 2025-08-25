#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试GUI基本功能
"""

import tkinter as tk
from tkinter import ttk, messagebox

def test_basic_gui():
    """测试基本GUI功能"""
    root = tk.Tk()
    root.title("GUI测试")
    root.geometry("400x300")
    
    # 创建一些基本组件
    frame = ttk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    ttk.Label(frame, text="GUI测试界面", font=("Arial", 16)).pack(pady=10)
    
    def show_message():
        messagebox.showinfo("测试", "GUI工作正常！")
    
    ttk.Button(frame, text="测试按钮", command=show_message).pack(pady=10)
    
    # 添加一些输入组件
    ttk.Label(frame, text="测试输入:").pack(pady=(20, 5))
    entry = ttk.Entry(frame, width=30)
    entry.pack(pady=5)
    
    # 添加滑块
    ttk.Label(frame, text="测试滑块:").pack(pady=(20, 5))
    scale = ttk.Scale(frame, from_=0, to=100, orient=tk.HORIZONTAL)
    scale.pack(fill=tk.X, pady=5)
    
    root.mainloop()

if __name__ == "__main__":
    test_basic_gui()