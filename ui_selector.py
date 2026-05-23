from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from main_200 import (
    load_config, save_config, run_simulation_fast,
    DEFAULT_CONFIG, MIN_LAT, MAX_LAT, MIN_LON, MAX_LON,
    disabled_directions, LEVY_EXP_PRIMARY, LEVY_EXP_SECONDARY,
    get_grid_index, load_map
)


def select_file_ui():
    config = load_config()
    root = tk.Tk()
    root.title("Marine Simulation - File Selector")
    root.geometry("1200x900")

    # 原有变量定义完全不变...
    def validate_positive_integer(value):
        """验证输入是否为正整数"""
        if not value.strip():
            return True
        try:
            num = int(value)
            return num > 0
        except ValueError:
            return False

    def on_step_time_entry_change(*args):
        """处理步进时间缩放因子输入变化"""
        current_value = step_time_var.get()
        if not validate_positive_integer(current_value):
            if not current_value.strip():
                step_time_var.set("1")  # 空值默认设为1
            else:
                try:
                    # 尝试修正为最接近的正整数
                    num = int(float(current_value))
                    step_time_var.set(str(max(1, num)))
                except ValueError:
                    step_time_var.set("1")

    def browse_map_file():
        file_path = filedialog.askopenfilename(title="Select Map Excel File",
                                               filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")])
        if file_path:
            map_entry.delete(0, tk.END)
            map_entry.insert(0, file_path)

    def browse_temp_file():
        file_path = filedialog.askopenfilename(title="Select Temperature Excel File",
                                               filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")])
        if file_path:
            temp_entry.delete(0, tk.END)
            temp_entry.insert(0, file_path)

    def on_exit():
        try:
            direction_seed_input = direction_seed_entry.get().strip()
            direction_seed = int(
                direction_seed_input) if direction_seed_input and direction_seed_input != "Leave empty for random generation" else None
            levy_seed_input = levy_seed_entry.get().strip()
            levy_seed = int(levy_seed_input) if levy_seed_input and levy_seed_input != "Leave empty for random generation" else None

            # 确保从输入框获取最新的坐标值
            start_lat = float(start_lat_entry.get())
            start_lon = float(start_lon_entry.get())
            
            saved_config = {
                "number_of_agents": int(agents_entry.get()),
                "max_steps": int(steps_entry.get()),
                "enable_lifespan_limit": enable_lifespan_var.get(),
                "lifespan_years": float(lifespan_entry.get()),
                "current_influence_mode": current_mode_var.get(),
                "start_lat": start_lat,  # 使用从输入框获取的值
                "start_lon": start_lon,  # 使用从输入框获取的值
                "self_speed": float(self_speed_entry.get()),
                "pure_full_state_survival_days": round(float(pure_survival_entry.get()), 9),
                "direction_seed": direction_seed,
                "levy_seed": levy_seed,
                "enable_lifespan_terminal": enable_lifespan_terminal_var.get(),
                "direction_mode": direction_var.get(),  # 确保方向模式被保存
                "enable_b_supply": enable_b_supply_var.get(),  # 新增：B区域补给启用状态
                "b_supply_percent": float(b_supply_percent_entry.get()),  # 新增：B区域补给百分比
                "enable_dual_levy": dual_levy_var.get(),  # 新增：双LEVY_EXP模式启用状态
                "step_time_multiplier": int(step_time_var.get()),  # 新增：步进时间缩放因子
                "maximize_window": maximize_window_var.get(),  # 新增：最大化窗口
                "auto_save_visualization": auto_save_viz_var.get(),  # 新增：自动保存可视化
                "record_video": record_video_var.get()  # 新增：录制视频
            }
            save_config(saved_config)
            print("Configuration saved:", saved_config)  # Debug info
            print(f"DEBUG: Saved coordinates - lat={start_lat}, lon={start_lon}")  # Debug coordinates
        except ValueError as e:
            print(f"Error saving configuration: {e}")
            save_config(DEFAULT_CONFIG)
        root.destroy()

    # ---------------------- 修正1：优化方向模式切换逻辑（清空无效路径）----------------------
    def toggle_temp_file_state(*_):
        if direction_var.get() == "random":
            temp_entry.config(state="disabled")
            temp_entry.delete(0, tk.END)  # 关键：随机模式下清空输入框，避免传递空字符串
        else:
            temp_entry.config(state="normal")

    def run_simulation():
        direction_mode = direction_var.get()
        current_influence_mode = current_mode_var.get()
        enable_lifespan_limit = enable_lifespan_var.get()
        enable_lifespan_terminal = enable_lifespan_terminal_var.get()
        enable_global_simulation = enable_global_var.get()
        
        # 原有参数验证逻辑（寿命、经纬度、速度）完全不变...
        if enable_lifespan_limit:
            try:
                lifespan_years = float(lifespan_entry.get())
                max_life_seconds = lifespan_years * 365 * 24 * 3600
            except ValueError:
                messagebox.showerror("Input Error", "Lifespan limit must be a number (unit: years)")
                return
        else:
            max_life_seconds = 0

        try:
            start_lat = float(start_lat_entry.get())
            start_lon = float(start_lon_entry.get())
            if not (MIN_LAT <= start_lat <= MAX_LAT):
                messagebox.showerror("Input Error", f"Latitude must be between {MIN_LAT} and {MAX_LAT}")
                return
            if not (MIN_LON <= start_lon <= MAX_LON):
                messagebox.showerror("Input Error", f"Longitude must be between {MIN_LON} and {MAX_LON}")
                return
        except ValueError:
            messagebox.showerror("Input Error", "Latitude and Longitude must be valid numbers")
            return

        try:
            self_speed = float(self_speed_entry.get())
            if self_speed <= 0:
                messagebox.showerror("Input Error", "SELF_SPEED must be a positive number")
                return
        except ValueError:
            messagebox.showerror("Input Error", "SELF_SPEED must be a valid number")
            return

        # ---------------------- 修正2：强化文件路径验证+明确参数传递 ----------------------
        excel_path = map_entry.get().strip()
        # 处理temp_path：随机模式→None，加权模式→验证文件存在
        if direction_mode == "random":
            temp_path = None  # 明确设为None，与主程序判断匹配
        else:
            temp_path = temp_entry.get().strip()
            # 加权模式：验证路径非空且文件存在
            if not temp_path or not Path(temp_path).exists():
                messagebox.showerror("Error", "Temperature file is required for weighted mode!\nPlease select a valid Excel file.")
                return

        # 地图文件验证（原有逻辑不变）
        if not excel_path or not Path(excel_path).exists():
            messagebox.showerror("Error", "Please select a valid map Excel file")
            return

        # 后续初始位置检测、基础参数验证、地图尺寸检测逻辑完全不变...
        try:
            grid = load_map(excel_path)
            nrows, ncols = grid.shape
            lats_inc = np.linspace(MIN_LAT, MAX_LAT, nrows + 1)
            lons_inc = np.linspace(MIN_LON, MAX_LON, ncols + 1)
            start_idx = get_grid_index(start_lat, start_lon, lats_inc, lons_inc, nrows)
            if not start_idx:
                messagebox.showwarning("Start Location Warning", "Current launch location is outside the map grid range, Agent may not be able to move!")
            else:
                start_i, start_j = start_idx
                cell_type = grid[start_i, start_j].cell_type
                if cell_type == "Y":
                    messagebox.showerror("Start Location Error", "Current launch location is land (Y-type area), Agent cannot move!\nPlease change coordinates (suggest selecting ocean area, e.g., lat=0.0, lon=0.0).")
                    return
                elif cell_type not in ("B", "G"):
                    messagebox.showwarning("Start Location Warning", f"Current launch location is unknown type ({cell_type}), may affect movement!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to verify start location: {e}")
            return

        try:
            n_agents = int(agents_entry.get())
            max_steps = int(steps_entry.get())
            direction_seed_input = direction_seed_entry.get().strip()
            direction_seed = int(direction_seed_input) if direction_seed_input and direction_seed_input != "Leave empty for random generation" else None
            levy_seed_input = levy_seed_entry.get().strip()
            levy_seed = int(levy_seed_input) if levy_seed_input and levy_seed_input != "Leave empty for random generation" else None
            pure_survival_days = float(pure_survival_entry.get())
            
            # 从StringVar获取步进时间缩放因子，已经有验证确保值是正整数
            step_time_multiplier = int(step_time_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Number of Agents、Max Steps、Direction Seed、Levy Seed must be integers")
            return

        try:
            df_map = pd.read_excel(excel_path, header=None)
            nrows, ncols = df_map.shape
            messagebox.showinfo("Map Detection", f"Detected map size: {nrows} × {ncols}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read map file: {e}")
            return

        if direction_mode == "weighted":
            try:
                df_temp = pd.read_excel(temp_path, header=None)
                trows, tcols = df_temp.shape
                if (trows, tcols) != (nrows, ncols):
                    messagebox.showerror("Size Mismatch", f"Map size: {nrows}×{ncols}\nTemperature file size: {trows}×{tcols}\n\nPlease select matching files.")
                    return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read temperature file: {e}")
                return

        # ---------------------- 修正3：确保传递所有参数（含direction_mode） ----------------------
        on_exit()
        if dual_levy_var.get():
            messagebox.showinfo("Dual LEVY_EXP Mode", f"First simulation: LEVY_EXP = {LEVY_EXP_PRIMARY}\nClose the first window to start the second simulation (LEVY_EXP = {LEVY_EXP_SECONDARY})")
            run_simulation_fast(
                excel_path=excel_path,
                n_agents=n_agents,
                max_steps=max_steps,
                direction_seed=direction_seed,
                levy_seed=levy_seed,
                temp_path=temp_path,
                levy_exp=LEVY_EXP_PRIMARY,
                enable_lifespan_terminal=enable_lifespan_terminal,
                max_life_seconds=max_life_seconds,
                direction_mode=direction_mode,  # 确保传递UI选择的模式
                show_interactive = True,  # 第一个模拟显示交互窗口
                enable_global_simulation=enable_global_simulation,  # 添加参数
                start_lat=start_lat,  # 修复：传递起始纬度
                start_lon=start_lon,  # 修复：传递起始经度
                self_speed=self_speed,  # 修复：传递自身速度
                pure_survival_days=pure_survival_days,  # 修复：传递纯生存天数
                current_influence_mode=current_influence_mode,  # 修复：传递当前影响模式
                enable_lifespan_limit=enable_lifespan_limit,  # 修复：传递寿命限制启用状态
                lifespan_years=lifespan_years if enable_lifespan_limit else 0,  # 修复：传递寿命年限
                step_time_multiplier=step_time_multiplier,  # 新增：步进时间缩放因子
                maximize_window=maximize_window_var.get(),  # 新增：最大化窗口
                auto_save_visualization=auto_save_viz_var.get(),  # 新增：自动保存可视化
                record_video=record_video_var.get()  # 新增：录制视频
            )
            # 新增：强制关闭所有图形窗口，释放资源
            import matplotlib.pyplot as plt
            plt.close('all')
            # 第二个模拟
            import gc
            import time
            # 1. 关闭所有matplotlib图形窗口
            print("Cleaning resources, preparing for second simulation...")
            plt.close('all')

            # 2. Force garbage collection
            gc.collect()

            # 3. Brief wait to ensure resource release
            time.sleep(2)

            # 4. Additional Tkinter cleanup
            try:
                # Get and destroy all Tkinter top-level windows
                import tkinter as tk
                for widget in tk._default_root.winfo_children():
                    try:
                        widget.destroy()
                    except:
                        pass
                # Update interface
                tk._default_root.update()
            except Exception as e:
                print(f"Tkinter cleanup warning: {e}")

            # 5. Garbage collection again
            gc.collect()

            print("Resource cleanup completed, starting second simulation...")
            # 第二个模拟
            run_simulation_fast(
                excel_path=excel_path,
                n_agents=n_agents,
                max_steps=max_steps,
                direction_seed=direction_seed,
                levy_seed=levy_seed,
                temp_path=temp_path,
                levy_exp=LEVY_EXP_SECONDARY,
                enable_lifespan_terminal=enable_lifespan_terminal,
                max_life_seconds=max_life_seconds,
                direction_mode=direction_mode,
                show_interactive=True,  # 第二个模拟显示交互窗口
                enable_global_simulation=enable_global_simulation,  # 新增
                start_lat=start_lat,  # 修复：传递起始纬度
                start_lon=start_lon,  # 修复：传递起始经度
                self_speed=self_speed,  # 修复：传递自身速度
                pure_survival_days=pure_survival_days,  # 修复：传递纯生存天数
                current_influence_mode=current_influence_mode,  # 修复：传递当前影响模式
                enable_lifespan_limit=enable_lifespan_limit,  # 修复：传递寿命限制启用状态
                lifespan_years=lifespan_years if enable_lifespan_limit else 0,  # 修复：传递寿命年限
                step_time_multiplier=step_time_multiplier,  # 新增：步进时间缩放因子
                maximize_window=maximize_window_var.get(),  # 新增：最大化窗口
                auto_save_visualization=auto_save_viz_var.get(),  # 新增：自动保存可视化
                record_video=record_video_var.get()  # 新增：录制视频
            )
            gc.collect()
        else:
            run_simulation_fast(
                excel_path=excel_path,
                n_agents=n_agents,
                max_steps=max_steps,
                direction_seed=direction_seed,
                levy_seed=levy_seed,
                temp_path=temp_path,
                levy_exp=LEVY_EXP_PRIMARY,
                enable_lifespan_terminal=enable_lifespan_terminal,
                max_life_seconds=max_life_seconds,
                direction_mode=direction_mode,  # 确保传递UI选择的模式
                enable_global_simulation=enable_global_simulation,  # 添加参数
                start_lat=start_lat,  # 修复：传递起始纬度
                start_lon=start_lon,  # 修复：传递起始经度
                self_speed=self_speed,  # 修复：传递自身速度
                pure_survival_days=pure_survival_days,  # 修复：传递纯生存天数
                current_influence_mode=current_influence_mode,  # 修复：传递当前影响模式
                enable_lifespan_limit=enable_lifespan_limit,  # 修复：传递寿命限制启用状态
                lifespan_years=lifespan_years if enable_lifespan_limit else 0,  # 修复：传递寿命年限
                step_time_multiplier=step_time_multiplier,  # 新增：步进时间缩放因子
                maximize_window=maximize_window_var.get(),  # 新增：最大化窗口
                auto_save_visualization=auto_save_viz_var.get(),  # 新增：自动保存可视化
                record_video=record_video_var.get()  # 新增：录制视频
            )
    # ---- UI控件布局（完全保持不变） ---------------------------------------
    LABEL_WIDTH = 25
    ENTRY_WIDTH = 20
    PADX = 10
    PADY_SMALL = 3
    PADY_LARGE = 8
    # 1. 文件选择区（row=0）
    file_frame = ttk.LabelFrame(root, text="File Selection (Required)", relief=tk.GROOVE)
    file_frame.grid(row=0, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(file_frame, text="Map File (xlsx):", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX, pady=PADY_SMALL,
                                                                           sticky="w")
    map_entry = ttk.Entry(file_frame, width=50)
    map_entry.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL)
    ttk.Button(file_frame, text="Browse", command=browse_map_file).grid(row=0, column=2, padx=PADX, pady=PADY_SMALL)
    ttk.Label(file_frame, text="Temperature File (xlsx):", width=LABEL_WIDTH).grid(row=1, column=0, padx=PADX,
                                                                                   pady=PADY_SMALL, sticky="w")
    temp_entry = ttk.Entry(file_frame, width=50)
    temp_entry.grid(row=1, column=1, padx=PADX, pady=PADY_SMALL)
    ttk.Button(file_frame, text="Browse", command=browse_temp_file).grid(row=1, column=2, padx=PADX, pady=PADY_SMALL)

    # 2. 基础模拟参数区（row=1）
    basic_frame = ttk.LabelFrame(root, text="Basic Simulation Parameters", relief=tk.GROOVE)
    basic_frame.grid(row=1, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(basic_frame, text="Number of Agents:", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX,
                                                                             pady=PADY_SMALL, sticky="w")
    agents_entry = ttk.Entry(basic_frame, width=ENTRY_WIDTH)
    agents_entry.insert(0, str(config["number_of_agents"]))
    agents_entry.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(basic_frame, text="Agent Self Speed:", width=LABEL_WIDTH).grid(row=0, column=2, padx=PADX,
                                                                             pady=PADY_SMALL, sticky="w")
    self_speed_entry = ttk.Entry(basic_frame, width=ENTRY_WIDTH)
    self_speed_entry.insert(0, str(config["self_speed"]))
    self_speed_entry.grid(row=0, column=3, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(basic_frame, text="(Positive number only)", font=("Arial", 8)).grid(row=0, column=4, padx=PADX,
                                                                                  pady=PADY_SMALL, sticky="w")
    ttk.Label(basic_frame, text="Max Steps:", width=LABEL_WIDTH).grid(row=1, column=0, padx=PADX, pady=PADY_SMALL,
                                                                      sticky="w")
    steps_entry = ttk.Entry(basic_frame, width=ENTRY_WIDTH)
    steps_entry.insert(0, str(config["max_steps"]))
    steps_entry.grid(row=1, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(basic_frame, text="Pure Full State Survival Time:", width=LABEL_WIDTH).grid(row=1, column=2, padx=PADX,
                                                                                          pady=PADY_SMALL, sticky="w")
    pure_survival_entry = ttk.Entry(basic_frame, width=ENTRY_WIDTH)
    pure_survival_entry.insert(0, f"{config['pure_full_state_survival_days']:.9f}")
    pure_survival_entry.grid(row=1, column=3, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(basic_frame, text="(Unit: days, up to 9 decimals)", font=("Arial", 8)).grid(row=1, column=4, padx=PADX,
                                                                                          pady=PADY_SMALL, sticky="w")

    # 3. 种子设置区（row=2）
    seed_frame = ttk.LabelFrame(root, text="Seed Settings (For Reproducibility)", relief=tk.GROOVE)
    seed_frame.grid(row=2, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(seed_frame, text="Direction Seed (Controls random direction):", width=LABEL_WIDTH).grid(row=0, column=0,
                                                                                                      padx=PADX,
                                                                                                      pady=PADY_SMALL,
                                                                                                      sticky="w")
    direction_seed_entry = ttk.Entry(seed_frame, width=ENTRY_WIDTH)
    direction_seed = config.get("direction_seed")
    direction_seed_entry.insert(0, str(direction_seed) if direction_seed is not None else "Leave empty for random generation")
    direction_seed_entry.bind("<FocusIn>", lambda e: direction_seed_entry.delete(0,
                                                                                 tk.END) if direction_seed_entry.get() == "Leave empty for random generation" else None)
    direction_seed_entry.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(seed_frame, text="Levy Seed (Controls step time t):", width=LABEL_WIDTH).grid(row=0, column=2, padx=PADX,
                                                                                            pady=PADY_SMALL, sticky="w")
    levy_seed_entry = ttk.Entry(seed_frame, width=ENTRY_WIDTH)
    levy_seed = config.get("levy_seed")
    levy_seed_entry.insert(0, str(levy_seed) if levy_seed is not None else "Leave empty for random generation")
    levy_seed_entry.bind("<FocusIn>", lambda e: levy_seed_entry.delete(0,
                                                                       tk.END) if levy_seed_entry.get() == "Leave empty for random generation" else None)
    levy_seed_entry.grid(row=0, column=3, padx=PADX, pady=PADY_SMALL, sticky="w")

    # 4. 初始位置设置区（row=3）
    location_frame = ttk.LabelFrame(root, text="Start Location Settings", relief=tk.GROOVE)
    location_frame.grid(row=3, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(location_frame, text="Latitude:", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX, pady=PADY_SMALL,
                                                                        sticky="w")
    start_lat_entry = ttk.Entry(location_frame, width=ENTRY_WIDTH)
    start_lat_entry.insert(0, str(config["start_lat"]))
    start_lat_entry.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(location_frame, text=f"(Range: {MIN_LAT} ~ {MAX_LAT})", font=("Arial", 8)).grid(row=0, column=2,
                                                                                              padx=PADX,
                                                                                              pady=PADY_SMALL,
                                                                                              sticky="w")
    ttk.Label(location_frame, text="Longitude:", width=LABEL_WIDTH).grid(row=0, column=3, padx=PADX, pady=PADY_SMALL,
                                                                         sticky="w")
    start_lon_entry = ttk.Entry(location_frame, width=ENTRY_WIDTH)
    start_lon_entry.insert(0, str(config["start_lon"]))
    start_lon_entry.grid(row=0, column=4, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(location_frame, text=f"(Range: {MIN_LON} ~ {MAX_LON})", font=("Arial", 8)).grid(row=0, column=5,
                                                                                              padx=PADX,
                                                                                              pady=PADY_SMALL,
                                                                                              sticky="w")

    # 5. 模式选择区（row=4）
    mode_frame = ttk.LabelFrame(root, text="Mode Selection", relief=tk.GROOVE)
    mode_frame.grid(row=4, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(mode_frame, text="Direction Selection Mode:", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX,
                                                                                    pady=PADY_SMALL, sticky="w")
    direction_var = tk.StringVar(value=config["direction_mode"], master=root)
    direction_frame = ttk.Frame(mode_frame)
    direction_frame.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")

    def toggle_temp_file_state(*_):
        temp_entry.config(state="disabled" if direction_var.get() == "random" else "normal")

    ttk.Radiobutton(direction_frame, text="Weighted (50% random + 50% temperature)", variable=direction_var,
                    value="weighted", command=toggle_temp_file_state).pack(anchor="w")
    ttk.Radiobutton(direction_frame, text="Random (No temperature file needed)", variable=direction_var, value="random",
                    command=toggle_temp_file_state).pack(anchor="w")
    ttk.Label(mode_frame, text="Current Influence Mode:", width=LABEL_WIDTH).grid(row=0, column=3, padx=PADX,
                                                                                  pady=PADY_SMALL, sticky="w")
    current_mode_var = tk.StringVar(value=config["current_influence_mode"])
    ttk.Radiobutton(mode_frame, text="With Current", variable=current_mode_var, value="with_current").grid(row=0,
                                                                                                           column=4,
                                                                                                           padx=PADX,
                                                                                                           pady=PADY_SMALL,
                                                                                                           sticky="w")
    ttk.Radiobutton(mode_frame, text="No Current", variable=current_mode_var, value="no_current").grid(row=0, column=5,
                                                                                                       padx=PADX,
                                                                                                       pady=PADY_SMALL,
                                                                                                       sticky="w")

    # 6. 全球模拟选项区（row=5）- 新增的框架，放在模式选择区之后
    global_frame = ttk.LabelFrame(root, text="Global Simulation Settings", relief=tk.GROOVE)
    global_frame.grid(row=5, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")

    enable_global_var = tk.BooleanVar(value=config.get("enable_global_simulation", True))
    ttk.Checkbutton(
        global_frame,
        text="Enable Global Simulation (Allow crossing map boundaries)",
        variable=enable_global_var
    ).grid(row=0, column=0, columnspan=3, padx=PADX, pady=PADY_SMALL, sticky="w")

    # 7. B Area Supply Settings (row=6)
    b_supply_frame = ttk.LabelFrame(root, text="B Area Supply Settings", relief=tk.GROOVE)
    b_supply_frame.grid(row=6, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    
    enable_b_supply_var = tk.BooleanVar(value=config["enable_b_supply"])
    ttk.Checkbutton(b_supply_frame, text="Enable B Area Supply Function", variable=enable_b_supply_var).grid(row=0, column=0, 
                                                                                                padx=PADX, pady=PADY_SMALL, sticky="w")
    
    ttk.Label(b_supply_frame, text="B Area Supply Percentage:", width=LABEL_WIDTH).grid(row=0, column=1, padx=PADX, 
                                                                              pady=PADY_SMALL, sticky="w")
    b_supply_percent_entry = ttk.Entry(b_supply_frame, width=ENTRY_WIDTH)
    b_supply_percent_entry.insert(0, str(config["b_supply_percent"]))
    b_supply_percent_entry.grid(row=0, column=2, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(b_supply_frame, text="% (Relative to G area supply time)", font=("Arial", 8)).grid(row=0, column=3, 
                                                                                     padx=PADX, pady=PADY_SMALL, sticky="w")

    # 8. 方向禁用控制区（row=7）
    dir_disable_frame = ttk.LabelFrame(root, text="Movement Direction Disable", relief=tk.GROOVE)
    dir_disable_frame.grid(row=7, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(dir_disable_frame, text="Disable Directions (Click to toggle):", width=LABEL_WIDTH).grid(row=0, column=0,
                                                                                                       padx=PADX,
                                                                                                       pady=PADY_SMALL,
                                                                                                       sticky="w")
    dir_btn_frame = ttk.Frame(dir_disable_frame)
    dir_btn_frame.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")

    def toggle_direction(dir_key, button):
        disabled_directions[dir_key] = not disabled_directions[dir_key]
        button.config(relief="sunken" if disabled_directions[dir_key] else "raised",
                      bg="lightgray" if disabled_directions[dir_key] else "SystemButtonFace")

    btn_n = tk.Button(dir_btn_frame, text="↑ (North)", width=10, command=lambda: toggle_direction("N", btn_n))
    btn_s = tk.Button(dir_btn_frame, text="↓ (South)", width=10, command=lambda: toggle_direction("S", btn_s))
    btn_w = tk.Button(dir_btn_frame, text="← (West)", width=10, command=lambda: toggle_direction("W", btn_w))
    btn_e = tk.Button(dir_btn_frame, text="→ (East)", width=10, command=lambda: toggle_direction("E", btn_e))
    btn_n.grid(row=0, column=1, padx=5, pady=2)
    btn_w.grid(row=1, column=0, padx=5, pady=2)
    btn_e.grid(row=1, column=2, padx=5, pady=2)
    btn_s.grid(row=2, column=1, padx=5, pady=2)

    # 9. 步进时间控制区（row=8）
    step_time_frame = ttk.LabelFrame(root, text="Step Time Settings", relief=tk.GROOVE)
    step_time_frame.grid(row=8, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(step_time_frame, text="Step Time Multiplier:", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX,
                                                                                     pady=PADY_SMALL, sticky="w")
    step_time_var = tk.StringVar(value=str(config.get("step_time_multiplier", 1)))
    step_time_var.trace("w", on_step_time_entry_change)
    step_time_multiplier_entry = ttk.Entry(step_time_frame, width=ENTRY_WIDTH, textvariable=step_time_var)
    step_time_multiplier_entry.grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(step_time_frame, text="(Positive integer, multiplies each step duration)", font=("Arial", 8)).grid(row=0, column=2,
                                                                                                                padx=PADX,
                                                                                                                pady=PADY_SMALL,
                                                                                                                sticky="w")

    # 10. 高级控制区（row=9）
    advanced_frame = ttk.LabelFrame(root, text="Advanced Controls (Optional)", relief=tk.GROOVE)
    advanced_frame.grid(row=9, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")
    ttk.Label(advanced_frame, text="Lifespan Limit:", width=LABEL_WIDTH).grid(row=0, column=0, padx=PADX,
                                                                              pady=PADY_SMALL, sticky="w")
    enable_lifespan_var = tk.BooleanVar(value=config["enable_lifespan_limit"])
    ttk.Checkbutton(advanced_frame, text="Enable Lifespan Limit", variable=enable_lifespan_var).grid(row=0, column=1,
                                                                                                     padx=PADX,
                                                                                                     pady=PADY_SMALL,
                                                                                                     sticky="w")
    lifespan_entry = ttk.Entry(advanced_frame, width=ENTRY_WIDTH)
    lifespan_entry.insert(0, str(config["lifespan_years"]))
    lifespan_entry.grid(row=0, column=2, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(advanced_frame, text="(Unit: years)", font=("Arial", 8)).grid(row=0, column=3, padx=PADX, pady=PADY_SMALL,
                                                                            sticky="w")
    ttk.Label(advanced_frame, text="Simulation Termination:", width=LABEL_WIDTH).grid(row=1, column=0, padx=PADX,
                                                                                      pady=PADY_SMALL, sticky="w")
    enable_lifespan_terminal_var = tk.BooleanVar(value=config["enable_lifespan_terminal"])
    ttk.Checkbutton(advanced_frame, text="Terminate by Agent's Total Lifespan (Ignore Max Steps)",
                    variable=enable_lifespan_terminal_var).grid(row=1, column=1, columnspan=3, padx=PADX,
                                                                pady=PADY_SMALL, sticky="w")
    ttk.Label(advanced_frame, text="Dual LEVY_EXP Mode:", width=LABEL_WIDTH).grid(row=2, column=0, padx=PADX,
                                                                                  pady=PADY_SMALL, sticky="w")
    dual_levy_var = tk.BooleanVar(value=config["enable_dual_levy"])
    ttk.Checkbutton(advanced_frame, text="Run both LEVY_EXP simulations (Serial Execution)",
                    variable=dual_levy_var).grid(row=2, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")
    ttk.Label(advanced_frame, text="(Modify LEVY_EXP_PRIMARY/SECONDARY in main_200.py)", font=("Arial", 8)).grid(row=2,
                                                                                                                 column=2,
                                                                                                                 columnspan=2,
                                                                                                                 padx=PADX,
                                                                                                                 pady=PADY_SMALL, sticky="w")

    # 11. 可视化设置区（row=10）
    viz_frame = ttk.LabelFrame(root, text="Visualization Settings", relief=tk.GROOVE)
    viz_frame.grid(row=10, column=0, columnspan=3, padx=PADX, pady=PADY_LARGE, sticky="we")

    maximize_window_var = tk.BooleanVar(value=config.get("maximize_window", False))
    ttk.Checkbutton(viz_frame, text="Maximize Simulation Window (After Completion)",
                    variable=maximize_window_var).grid(row=0, column=0, padx=PADX, pady=PADY_SMALL, sticky="w")

    auto_save_viz_var = tk.BooleanVar(value=config.get("auto_save_visualization", False))
    ttk.Checkbutton(viz_frame, text="Auto-save Visualization During Simulation",
                    variable=auto_save_viz_var).grid(row=0, column=1, padx=PADX, pady=PADY_SMALL, sticky="w")

    record_video_var = tk.BooleanVar(value=config.get("record_video", False))
    ttk.Checkbutton(viz_frame, text="Record Simulation Video",
                    variable=record_video_var).grid(row=0, column=2, padx=PADX, pady=PADY_SMALL, sticky="w")

    button_frame = ttk.Frame(root)
    button_frame.grid(row=11, column=0, columnspan=3, pady=20, sticky="we")
    # 为按钮添加样式（如果需要）
    style = ttk.Style()
    style.configure("Accent.TButton", font=("Arial", 10, "bold"))
    run_button = ttk.Button(button_frame, text="Run Simulation", command=run_simulation, style="Accent.TButton")
    exit_button = ttk.Button(button_frame, text="Exit", command=on_exit)
    run_button.pack(side="right", padx=(0, 10))
    exit_button.pack(side="right", padx=(10, 20))

    # 初始化配置
    toggle_temp_file_state()
    root.grid_columnconfigure(0, weight=1)
    root.mainloop()


# UI脚本主入口
if __name__ == "__main__":
    plt.switch_backend('TkAgg')
    select_file_ui()