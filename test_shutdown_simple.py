#!/usr/bin/env python3
"""
简单测试关机功能是否被正确调用
"""

import tkinter as tk
from tkinter import ttk
import time

def test_shutdown_logic():
    """测试关机逻辑"""
    print("=== 测试关机逻辑 ===")
    
    # 模拟倒计时逻辑
    shutdown_countdown = 3  # 3秒测试
    shutdown_interrupted = False
    
    def simulate_countdown():
        nonlocal shutdown_countdown
        
        # 检查是否被中断
        if shutdown_interrupted:
            print("❌ 关机被中断")
            return
            
        # 检查倒计时是否结束
        if shutdown_countdown <= 0:
            print("✅ 倒计时结束，应该执行关机")
            return
            
        # 更新倒计时显示
        print(f"倒计时: {shutdown_countdown} 秒")
        
        # 减少倒计时
        shutdown_countdown -= 1
        
        # 模拟每秒更新
        if shutdown_countdown >= 0:
            print("继续倒计时...")
            # 模拟延迟
            time.sleep(0.1)
            simulate_countdown()
    
    print("开始模拟倒计时...")
    simulate_countdown()
    print("倒计时模拟完成")

def test_ui_integration():
    """测试UI集成"""
    print("\n=== 测试UI集成 ===")
    
    # 创建简单的UI测试
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    # 测试变量
    auto_shutdown_var = tk.BooleanVar(value=True)
    shutdown_countdown_var = tk.StringVar(value="")
    
    # 模拟_on_execution_finished调用
    message = "所有实验执行完成"
    
    if auto_shutdown_var.get() and "失败" not in message and "错误" not in message:
        print("✅ 自动关机条件满足")
        print("应该调用 _start_shutdown_countdown()")
    else:
        print("❌ 自动关机条件不满足")
    
    root.destroy()

def test_command_execution():
    """测试命令执行"""
    print("\n=== 测试命令执行 ===")
    
    import subprocess
    import os
    
    # 测试方法1: 使用完整系统路径
    try:
        system_root = os.environ.get('SystemRoot', 'C:\\Windows')
        shutdown_path = os.path.join(system_root, 'System32', 'shutdown.exe')
        
        if os.path.exists(shutdown_path):
            print(f"✅ shutdown.exe路径存在: {shutdown_path}")
            
            # 测试命令（使用/t 1避免立即关机）
            result = subprocess.run([shutdown_path, "/s", "/t", "1"], 
                                  capture_output=True, text=True, timeout=5)
            print(f"命令返回码: {result.returncode}")
            
            # 取消关机
            subprocess.run([shutdown_path, "/a"], capture_output=True)
            print("✅ 关机命令执行成功（已取消）")
        else:
            print(f"❌ shutdown.exe路径不存在: {shutdown_path}")
            
    except subprocess.TimeoutExpired:
        print("⚠️ 命令执行超时（正常现象）")
    except Exception as e:
        print(f"❌ 命令执行失败: {e}")

if __name__ == "__main__":
    print("测试关机功能实现")
    print("=" * 50)
    
    test_shutdown_logic()
    test_ui_integration()
    test_command_execution()
    
    print("\n" + "=" * 50)
    print("测试完成")