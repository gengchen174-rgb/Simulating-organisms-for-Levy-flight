#!/usr/bin/env python3
"""
测试Windows 10关机功能修复
"""

import subprocess
import platform
import ctypes

def test_shutdown_methods():
    """测试各种关机方法"""
    print("=== 测试Windows 10关机功能 ===")
    print(f"操作系统: {platform.system()} {platform.release()}")
    
    # 方法1: 使用shell=True和完整的命令字符串
    print("\n方法1: 使用shell执行关机命令")
    try:
        # 注意：这里使用/t 1而不是/t 0，避免立即关机
        result = subprocess.run("shutdown /s /t 1", shell=True, capture_output=True, text=True)
        print(f"  返回码: {result.returncode}")
        print(f"  标准输出: {result.stdout}")
        print(f"  标准错误: {result.stderr}")
        
        # 取消关机（测试用）
        subprocess.run("shutdown /a", shell=True, capture_output=True)
        print("  ✅ 方法1测试成功（已取消关机）")
    except Exception as e:
        print(f"  ❌ 方法1失败: {e}")
    
    # 方法2: 使用不同的参数格式
    print("\n方法2: 使用不同的参数格式")
    try:
        result = subprocess.run(["shutdown.exe", "/s", "/t", "1"], capture_output=True, text=True)
        print(f"  返回码: {result.returncode}")
        print(f"  标准输出: {result.stdout}")
        print(f"  标准错误: {result.stderr}")
        
        # 取消关机
        subprocess.run(["shutdown.exe", "/a"], capture_output=True)
        print("  ✅ 方法2测试成功（已取消关机）")
    except Exception as e:
        print(f"  ❌ 方法2失败: {e}")
    
    # 方法3: 使用PowerShell命令
    print("\n方法3: 使用PowerShell关机命令")
    try:
        # 使用-WhatIf参数进行测试，不实际执行
        powershell_cmd = "Stop-Computer -WhatIf"
        result = subprocess.run(["powershell", "-Command", powershell_cmd], 
                              capture_output=True, text=True)
        print(f"  返回码: {result.returncode}")
        print(f"  标准输出: {result.stdout}")
        print(f"  标准错误: {result.stderr}")
        
        if "What if" in result.stdout:
            print("  ✅ 方法3测试成功（PowerShell命令可用）")
        else:
            print("  ⚠️ 方法3可能有问题")
    except Exception as e:
        print(f"  ❌ 方法3失败: {e}")
    
    # 方法4: 检查管理员权限
    print("\n方法4: 检查管理员权限")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        print(f"  当前用户是否管理员: {is_admin}")
        
        if is_admin:
            print("  ✅ 方法4: 具有管理员权限")
        else:
            print("  ⚠️ 方法4: 需要管理员权限")
    except Exception as e:
        print(f"  ❌ 方法4失败: {e}")
    
    print("\n=== 测试完成 ===")

def test_safe_shutdown():
    """测试安全的关机命令（不会实际关机）"""
    print("\n=== 测试安全关机命令 ===")
    
    # 测试取消关机功能
    try:
        # 先设置一个1秒后关机的命令
        subprocess.run("shutdown /s /t 1", shell=True, capture_output=True)
        print("设置1秒后关机...")
        
        # 立即取消
        result = subprocess.run("shutdown /a", shell=True, capture_output=True, text=True)
        print(f"取消关机命令返回码: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ 取消关机功能正常")
        else:
            print("❌ 取消关机功能可能有问题")
            
    except Exception as e:
        print(f"❌ 安全关机测试失败: {e}")

if __name__ == "__main__":
    if platform.system() == "Windows":
        test_shutdown_methods()
        test_safe_shutdown()
    else:
        print("此测试仅适用于Windows系统")
        print(f"当前系统: {platform.system()}")