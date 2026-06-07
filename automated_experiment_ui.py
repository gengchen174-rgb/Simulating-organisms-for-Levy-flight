"""
自动化实验执行器 - UI模块
负责用户界面相关的功能
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import sys
import os


class AutomatedExperimentUI:
    """自动化实验执行器UI类"""

    def __init__(self, core_logic):
        """
        初始化UI

        Args:
            core_logic: 核心逻辑模块实例
        """
        self.core_logic = core_logic
        self.root = tk.Tk()
        self.root.title("自动化实验组执行器")
        self.root.geometry("600x350")

        # 线程控制变量
        self.execution_thread = None
        self.is_running = False
        self.stop_requested = False
        self.ui_queue = queue.Queue()

        # 自动关机相关变量
        self.auto_shutdown_var = tk.BooleanVar(value=False)
        self.shutdown_countdown_var = tk.StringVar(value="")
        self.shutdown_timer = None
        self.shutdown_countdown = 0
        self.shutdown_interrupted = False
        self.shutdown_dialog = None

        # 初始化UI组件
        self.init_ui()

        # 设置UI更新定时器
        self.root.after(100, self.process_ui_queue)

    def init_ui(self):
        """初始化用户界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="自动化实验组执行器",
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))

        # 文件选择框架
        file_frame = ttk.LabelFrame(main_frame, text="配置文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 20))

        # 文件路径输入框和浏览按钮
        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)

        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_row, textvariable=self.file_path_var, state="readonly")
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = ttk.Button(file_row, text="浏览", command=self.browse_file)
        browse_btn.pack(side=tk.RIGHT)

        # 控制按钮框架
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        self.run_btn = ttk.Button(control_frame, text="开始执行",
                                 command=self.start_execution, state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(control_frame, text="停止执行",
                                  command=self.stop_execution, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # 自动关机选项框架
        shutdown_frame = ttk.LabelFrame(main_frame, text="自动关机选项", padding="10")
        shutdown_frame.pack(fill=tk.X, pady=(0, 10))

        # 自动关机复选框
        auto_shutdown_check = ttk.Checkbutton(shutdown_frame,
                                             text="实验完成后自动关闭电脑",
                                             variable=self.auto_shutdown_var)
        auto_shutdown_check.pack(anchor=tk.W)

        # 倒计时显示标签
        countdown_label = ttk.Label(shutdown_frame, textvariable=self.shutdown_countdown_var,
                                   font=("Arial", 10, "italic"))
        countdown_label.pack(anchor=tk.W, pady=(5, 0))

        # 进度显示框架
        progress_frame = ttk.LabelFrame(main_frame, text="执行进度", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True)

        # 进度条
        self.progress_var = tk.DoubleVar(value=0.0)
        progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                      maximum=100.0)
        progress_bar.pack(fill=tk.X, pady=(0, 10))

        # 状态文本
        self.status_var = tk.StringVar(value="等待开始...")
        status_label = ttk.Label(progress_frame, textvariable=self.status_var)
        status_label.pack()

    def browse_file(self):
        """浏览并选择配置文件"""
        file_path = filedialog.askopenfilename(
            title="选择自动化配置文件",
            filetypes=[("CSV Files", "*.csv"), ("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.core_logic.automation_file_path = file_path
            self.run_btn.config(state=tk.NORMAL)
            self.log(f"已选择配置文件: {file_path}")

    def log(self, message):
        """添加日志信息 - 使用核心模块的日志系统"""
        # 使用核心模块的日志系统，避免重复输出
        if hasattr(self, 'core_logic') and hasattr(self.core_logic, 'log'):
            self.core_logic.log(message)
        else:
            # 备用方案：直接打印（无时间戳）
            print(f"{message}")

    def process_ui_queue(self):
        """处理UI更新队列，确保线程安全的UI更新"""
        try:
            while True:
                # 非阻塞方式获取队列中的任务
                try:
                    task = self.ui_queue.get_nowait()
                    if task is None:  # 停止信号
                        break
                    task()  # 执行UI更新任务
                except queue.Empty:
                    break
        except Exception as e:
            print(f"处理UI队列时出错: {e}")

        # 继续设置定时器处理队列
        if not self.stop_requested:
            self.root.after(100, self.process_ui_queue)

    def _update_progress(self, progress, status):
        """线程安全的UI进度更新"""
        try:
            if hasattr(self, 'progress_var') and hasattr(self, 'status_var'):
                self.progress_var.set(progress)
                self.status_var.set(status)
        except Exception as e:
            print(f"更新进度失败: {e}")

    def _on_execution_finished(self, message):
        """执行完成后的UI更新"""
        self.is_running = False
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set(message)

        if "失败" in message or "错误" in message:
            messagebox.showerror("执行失败", message)
        else:
            messagebox.showinfo("执行完成", message)

    def start_execution(self):
        """开始执行实验"""
        if not self.core_logic.automation_file_path:
            messagebox.showerror("错误", "请先选择配置文件")
            return

        self.is_running = True
        self.stop_requested = False
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("正在启动执行线程...")

        # 启动后台执行线程
        self.execution_thread = threading.Thread(target=self._run_simulation_in_thread)
        self.execution_thread.daemon = True
        self.execution_thread.start()

        self.log("后台执行线程已启动，UI将保持响应")

    def _run_simulation_in_thread(self):
        """在后台线程中执行模拟"""
        try:
            # 通过UI队列更新状态
            self.ui_queue.put(lambda: self._update_progress(0, "正在执行实验..."))

            # 调用核心逻辑模块执行实验
            self.core_logic.execute_all_experiments(self.ui_queue, self._update_progress)

            # 执行完成
            self.ui_queue.put(lambda: self._on_execution_finished("所有实验执行完成"))

        except Exception as e:
            error_msg = f"执行过程中出错: {e}"
            self.log(error_msg)
            self.ui_queue.put(lambda: self._on_execution_finished(error_msg))

    def stop_execution(self):
        """停止执行"""
        if self.is_running:
            self.stop_requested = True
            self.status_var.set("正在停止执行...")
            self.log("用户请求停止执行")

    def _safe_cleanup_matplotlib(self):
        """在主线程中安全清理Matplotlib资源"""
        try:
            import matplotlib.pyplot as plt
            # 在主线程中清理Matplotlib资源
            plt.close('all')
            self.log("Matplotlib资源清理完成")
        except Exception as e:
            self.log(f"Matplotlib资源清理失败: {e}")

    def _on_execution_finished(self, message):
        """执行完成后的处理"""
        self.is_running = False
        self.status_var.set(message)
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        # 执行完成后在主线程中安全清理Matplotlib资源
        self._safe_cleanup_matplotlib()

        # 如果启用了自动关机，开始关机倒计时
        if self.auto_shutdown_var.get() and "失败" not in message and "错误" not in message:
            self._start_shutdown_countdown()

    def _start_shutdown_countdown(self):
        """开始关机倒计时"""
        self.shutdown_countdown = 10  # 10秒倒计时
        self.shutdown_interrupted = False

        # 创建关机确认对话框
        self._create_shutdown_dialog()

        # 开始倒计时
        self._update_shutdown_countdown()

    def _create_shutdown_dialog(self):
        """创建关机确认对话框"""
        # 创建顶层窗口
        self.shutdown_dialog = tk.Toplevel(self.root)
        self.shutdown_dialog.title("自动关机确认")
        self.shutdown_dialog.geometry("400x200")
        self.shutdown_dialog.resizable(False, False)
        self.shutdown_dialog.transient(self.root)  # 设置为主窗口的子窗口
        self.shutdown_dialog.grab_set()  # 模态对话框

        # 居中显示
        self.shutdown_dialog.update_idletasks()
        x = (self.shutdown_dialog.winfo_screenwidth() - self.shutdown_dialog.winfo_reqwidth()) // 2
        y = (self.shutdown_dialog.winfo_screenheight() - self.shutdown_dialog.winfo_reqheight()) // 2
        self.shutdown_dialog.geometry(f"+{x}+{y}")

        # 对话框内容
        content_frame = ttk.Frame(self.shutdown_dialog, padding="20")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(content_frame, text="自动关机倒计时",
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))

        # 倒计时显示
        countdown_label = ttk.Label(content_frame,
                                   textvariable=self.shutdown_countdown_var,
                                   font=("Arial", 16, "bold"),
                                   foreground="red")
        countdown_label.pack(pady=10)

        # 提示信息
        info_label = ttk.Label(content_frame,
                              text="实验已完成，系统将在倒计时结束后自动关机",
                              font=("Arial", 10))
        info_label.pack(pady=(0, 20))

        # 中断按钮
        interrupt_btn = ttk.Button(content_frame, text="中断关机",
                                   command=self._interrupt_shutdown)
        interrupt_btn.pack()

    def _update_shutdown_countdown(self):
        """更新关机倒计时"""
        # 检查是否被中断
        if self.shutdown_interrupted:
            return
            
        # 检查倒计时是否结束
        if self.shutdown_countdown <= 0:
            # 倒计时结束，执行关机
            self._execute_shutdown()
            return

        # 更新倒计时显示
        self.shutdown_countdown_var.set(f"倒计时: {self.shutdown_countdown} 秒")

        # 减少倒计时
        self.shutdown_countdown -= 1
        
        # 每秒更新一次，直到倒计时结束
        if self.shutdown_countdown >= 0:
            self.shutdown_timer = self.root.after(1000, self._update_shutdown_countdown)

    def _interrupt_shutdown(self):
        """中断关机"""
        self.shutdown_interrupted = True
        self.shutdown_countdown_var.set("关机已中断")

        # 取消定时器
        if self.shutdown_timer:
            self.root.after_cancel(self.shutdown_timer)
            self.shutdown_timer = None

        # 关闭对话框
        if self.shutdown_dialog:
            self.shutdown_dialog.destroy()
            self.shutdown_dialog = None

        self.log("用户中断了自动关机")

    def _execute_shutdown(self):
        """执行系统关机"""
        try:
            self.log("正在执行系统关机...")

            # 关闭对话框
            if self.shutdown_dialog:
                self.shutdown_dialog.destroy()
                self.shutdown_dialog = None

            # 执行关机命令
            import subprocess
            import platform
            import os

            system = platform.system()
            if system == "Windows":
                # Windows系统关机命令 - 优化Windows 10兼容性
                self.log("检测到Windows系统，执行关机命令...")

                # 方法1: 使用完整的系统路径和shell执行（最可靠的方法）
                try:
                    self.log("执行方法1: 使用系统路径关机命令")
                    # 使用完整的系统路径，避免PATH环境变量问题
                    system_root = os.environ.get('SystemRoot', 'C:\\Windows')
                    shutdown_path = os.path.join(system_root, 'System32', 'shutdown.exe')

                    if os.path.exists(shutdown_path):
                        # 使用完整路径执行关机命令
                        subprocess.run([shutdown_path, "/s", "/t", "0"], check=True, timeout=10)
                        self.log("方法1执行成功 - 系统将在0秒后关机")
                        return
                    else:
                        self.log(f"未找到shutdown.exe: {shutdown_path}")
                except subprocess.TimeoutExpired:
                    self.log("方法1: 关机命令执行超时（正常现象）")
                    return
                except Exception as e1:
                    self.log(f"方法1失败: {e1}")

                # 方法2: 使用shell执行（备用方法）
                try:
                    self.log("执行方法2: 使用shell执行关机命令")
                    # 使用shell=True，确保命令解析正确
                    result = subprocess.run("shutdown /s /t 0", shell=True,
                                          capture_output=True, text=True, timeout=10)

                    if result.returncode == 0:
                        self.log("方法2执行成功 - 系统将在0秒后关机")
                        return
                    else:
                        self.log(f"方法2返回码非零: {result.returncode}")
                        self.log(f"标准错误: {result.stderr}")
                except subprocess.TimeoutExpired:
                    self.log("方法2: 关机命令执行超时（正常现象）")
                    return
                except Exception as e2:
                    self.log(f"方法2失败: {e2}")

                # 方法3: 使用PowerShell命令（最终备用）
                try:
                    self.log("执行方法3: 使用PowerShell关机命令")
                    powershell_cmd = "Stop-Computer -Force"
                    result = subprocess.run(["powershell", "-Command", powershell_cmd],
                                          capture_output=True, text=True, timeout=10)

                    if result.returncode == 0:
                        self.log("方法3执行成功 - 系统将立即关机")
                        return
                    else:
                        self.log(f"方法3返回码非零: {result.returncode}")
                        self.log(f"标准错误: {result.stderr}")
                except subprocess.TimeoutExpired:
                    self.log("方法3: 关机命令执行超时（正常现象）")
                    return
                except Exception as e3:
                    self.log(f"方法3失败: {e3}")

                # 所有方法都失败
                error_msg = "所有Windows关机方法都失败，请检查：\n"
                error_msg += "1. 系统权限是否足够\n"
                error_msg += "2. shutdown.exe是否在系统路径中\n"
                error_msg += "3. 是否被安全软件阻止"
                raise Exception(error_msg)

            elif system == "Linux":
                # Linux系统关机命令
                subprocess.run(["shutdown", "-h", "now"], check=True)
            elif system == "Darwin":  # macOS
                subprocess.run(["shutdown", "-h", "now"], check=True)
            else:
                self.log(f"不支持的系统: {system}")
                return

            self.log("系统关机命令已执行")

        except Exception as e:
            self.log(f"执行关机命令失败: {e}")
            # 显示错误信息
            if self.shutdown_dialog:
                self.shutdown_countdown_var.set(f"关机失败: {e}")
            else:
                messagebox.showerror("关机失败", f"无法执行关机命令: {e}")

    def run(self):
        """运行UI主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    # 测试UI模块
    from automated_experiment_core import AutomatedExperimentCore

    core = AutomatedExperimentCore()
    ui = AutomatedExperimentUI(core)
    ui.run()