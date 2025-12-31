"""
全球迁移功能测试脚本
测试跨越经纬度边界的agent迁移功能
"""

from __future__ import annotations
import math
import random
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import threading
import time

# 导入必要的模块
from simulation_constants import (
    MIN_LAT, MAX_LAT, MIN_LON, MAX_LON,
    M_PER_DEG_LAT, SELF_SPEED, CURRENT_SPEED,
    LEVY_SCALE, LEVY_EXP_PRIMARY,
    start_lat, start_lon, DEFAULT_AGENTS, DEFAULT_STEPS,
    ENABLE_LIFESPAN_LIMIT, LIFESPAN_YEARS, TEMP_SCORE,
    direction_mode, disabled_directions, current_influence_mode
)

# 从 simulation_utils 导入工具函数
try:
    from simulation_utils import (
        GridCell, parse_cell, load_map,
        bresenham_line, get_grid_index, locate_cell,
        load_config, save_config, load_max_migration_seconds
    )
except ImportError:
    print("Warning: Cannot import simulation_utils module")

# 从 global_simulation_utils 导入全球模拟函数
try:
    from global_simulation_utils import (
        normalize_coordinates,
        adjust_direction_for_pole_crossing,
        get_wrap_around_offset,
        GlobalPathManager,
        plot_global_paths
    )

    GLOBAL_SIM_AVAILABLE = True
except ImportError:
    GLOBAL_SIM_AVAILABLE = False
    print("Warning: global_simulation_utils module not found")

# 全局变量
MAX_MIGRATION_SECONDS = 24 * 3600 * 100000  # 极大的补给时间，接近无限
SIMULATION_RUNNING = False
PREFERRED_DIRECTION = None  # 用户选择的方向偏好
PREFERRED_DIRECTION_PROB = 0.3  # 偏好方向的概率

# 方向区间定义
DIRECTION_RANGES = {
    'N': (315, 45),  # 北方向：315°到45°（跨越0°）
    'E': (45, 135),  # 东方向：45°到135°
    'S': (135, 225),  # 南方向：135°到225°
    'W': (225, 315)  # 西方向：225°到315°
}


def get_direction_angle(preferred_dir=None):
    """
    根据偏好方向获取角度

    规则:
    - 如果指定了偏好方向，有70%概率返回该方向区间内的随机角度
    - 其他30%概率平均分配到其他三个方向（每个方向10%概率）

    参数:
        preferred_dir: 偏好方向 ('N', 'E', 'S', 'W') 或 None

    返回:
        角度值 (0-360度)
    """
    if preferred_dir is None:
        # 没有偏好方向，完全随机
        return random.uniform(0, 360)

    # 检查是否为偏好方向
    if random.random() < PREFERRED_DIRECTION_PROB:
        # 70%概率：在偏好方向区间内随机选择
        start_angle, end_angle = DIRECTION_RANGES[preferred_dir]

        # 处理跨越0度的情况（北方向）
        if start_angle > end_angle:
            # 角度范围跨越0度
            angle = random.uniform(start_angle, end_angle + 360)
            if angle >= 360:
                angle -= 360
        else:
            angle = random.uniform(start_angle, end_angle)

        return angle
    else:
        # 30%概率：在其他三个方向中随机选择一个
        other_directions = [d for d in DIRECTION_RANGES.keys() if d != preferred_dir]
        random_dir = random.choice(other_directions)

        # 在该方向区间内随机选择
        start_angle, end_angle = DIRECTION_RANGES[random_dir]

        if start_angle > end_angle:
            # 角度范围跨越0度
            angle = random.uniform(start_angle, end_angle + 360)
            if angle >= 360:
                angle -= 360
        else:
            angle = random.uniform(start_angle, end_angle)

        return angle


def direction_angle_to_cardinal(angle):
    """
    将角度转换为方向标签

    参数:
        angle: 角度值 (0-360度)

    返回:
        方向标签 ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
    """
    angle = angle % 360

    if 337.5 <= angle <= 360 or 0 <= angle < 22.5:
        return "N"
    elif 22.5 <= angle < 67.5:
        return "NE"
    elif 67.5 <= angle < 112.5:
        return "E"
    elif 112.5 <= angle < 157.5:
        return "SE"
    elif 157.5 <= angle < 202.5:
        return "S"
    elif 202.5 <= angle < 247.5:
        return "SW"
    elif 247.5 <= angle < 292.5:
        return "W"
    else:  # 292.5 <= angle < 337.5
        return "NW"


class GlobalTestAgent:
    """全球迁移测试Agent类"""

    def __init__(self, lat: float, lon: float, agent_id: int, self_speed: float = 100.0):
        self.lat = lat
        self.lon = lon
        self.agent_id = agent_id
        self.alive = True
        self.time_since_G = 0.0
        self.total_alive_seconds = 0.0
        self.death_type = None
        self.self_speed = self_speed
        self.enable_global_simulation = True  # 始终启用全球模拟

        # 路径管理
        self.global_path_manager = GlobalPathManager(agent_id)
        self.global_path_manager.add_point(lon, lat)  # 添加起点

        # 统计信息
        self.total_distance = 0.0
        self.boundary_crossings = 0
        self.pole_crossings = 0
        self.last_angle = 0.0

        # 新增：无效移动尝试计数器
        self.invalid_move_attempts = 0
        self.total_invalid_attempts = 0

    def step(self, grid, lats_inc, lons_inc, preferred_direction=None, max_attempts=50):
        """执行一步移动

        新增规则：如果移动终点为陆地(Y)，则重新选择步进时间和方向

        参数:
            max_attempts: 最大尝试次数，避免无限循环
        """
        if not self.alive:
            return

        # 记录当前尝试次数
        attempts = 0
        move_successful = False

        while not move_successful and attempts < max_attempts:
            attempts += 1
            self.invalid_move_attempts = attempts

            # 使用Levy飞行计算步长时间
            LEVY_TIME_SCALE = LEVY_SCALE / self.self_speed
            t = LEVY_TIME_SCALE * (random.paretovariate(LEVY_EXP_PRIMARY) + 1.0)

            # 累加总存活时间（即使移动无效，时间仍在流逝）
            self.total_alive_seconds += t

            # 选择移动方向
            alpha = get_direction_angle(preferred_direction)

            # 记录方向
            direction_label = direction_angle_to_cardinal(alpha)

            # 计算移动距离
            a = math.radians(alpha)
            v_self_e = self.self_speed * math.sin(a)
            v_self_n = self.self_speed * math.cos(a)

            # 获取当前单元格（如果有洋流）
            cell_start = locate_cell(self.lat, self.lon, grid, lats_inc, lons_inc, self.enable_global_simulation)

            if cell_start is not None and current_influence_mode == "with_current":
                v_cur_e, v_cur_n = cell_start.current_vector()
            else:
                v_cur_e, v_cur_n = 0.0, 0.0

            # 合成速度
            v_e = v_self_e + v_cur_e
            v_n = v_self_n + v_cur_n
            v_mag = math.hypot(v_e, v_n)

            if v_mag == 0.0:
                continue  # 速度为零，重新尝试

            # 计算位移
            d = v_mag * t

            dn = d * (v_n / v_mag)
            de = d * (v_e / v_mag)
            cosphi = max(1e-9, math.cos(math.radians(self.lat)))

            # 经纬度变化
            dlat = dn / M_PER_DEG_LAT
            dlon = de / (M_PER_DEG_LAT * cosphi)

            # 新位置（标准化前）
            new_lat = self.lat + dlat
            new_lon = self.lon + dlon

            # 检查是否跨越边界
            old_lon, old_lat = normalize_coordinates(self.lon, self.lat)
            new_norm_lon, new_norm_lat = normalize_coordinates(new_lon, new_lat)

            # 检查经度跨越
            if abs(old_lon - new_norm_lon) > 180:
                self.boundary_crossings += 1

            # 检查纬度跨越（极点）
            if (old_lat <= 90 and new_lat > 90) or (old_lat >= -90 and new_lat < -90):
                self.pole_crossings += 1

            # 标准化坐标
            norm_lon, norm_lat = normalize_coordinates(new_lon, new_lat)

            # 调整方向（如果穿越极点）
            adjusted_alpha = adjust_direction_for_pole_crossing(self.lat, new_lat, alpha)
            if adjusted_alpha != alpha:
                # 方向被调整了，说明穿越了极点
                alpha = adjusted_alpha

            # 检查目标单元格是否为陆地(Y)
            target_cell = locate_cell(norm_lat, norm_lon, grid, lats_inc, lons_inc, self.enable_global_simulation)

            # 新增规则：如果目标是陆地(Y)，则重新尝试
            if target_cell is not None and target_cell.cell_type == "Y":
                # 陆地，无效移动，重新尝试
                continue

            # 移动有效（浅海G或海洋B）
            move_successful = True

            # 更新距离
            self.total_distance += d

            # 更新角度
            self.last_angle = alpha

            # 更新坐标
            self.lat = norm_lat
            self.lon = norm_lon

            # 添加到路径管理器
            self.global_path_manager.add_point(new_lon, new_lat)

            # 检查是否在陆地上（这应该不会发生，因为上面已经检查过）
            if target_cell is not None and target_cell.cell_type == "Y":
                self.alive = False
                self.death_type = "land"

            # 重置尝试次数
            self.invalid_move_attempts = 0
            self.total_invalid_attempts += (attempts - 1)  # 记录无效尝试次数

        # 如果达到最大尝试次数仍未找到有效移动
        if not move_successful:
            # 可以选择：1. 保持原地不动 2. 随机选择一个有效方向强制移动
            # 这里选择保持原地不动
            print(f"Agent {self.agent_id}: Maximum move attempts reached ({max_attempts}), staying in place.")
            # 仍然记录时间流逝
            self.total_invalid_attempts += max_attempts

    def get_stats(self):
        """获取Agent统计信息"""
        return {
            "agent_id": self.agent_id,
            "alive": self.alive,
            "death_type": self.death_type,
            "total_time_seconds": self.total_alive_seconds,
            "total_distance_km": self.total_distance / 1000.0,
            "boundary_crossings": self.boundary_crossings,
            "pole_crossings": self.pole_crossings,
            "current_lat": self.lat,
            "current_lon": self.lon,
            "last_angle": self.last_angle,
            "last_direction": direction_angle_to_cardinal(self.last_angle),
            "total_invalid_attempts": self.total_invalid_attempts
        }


def run_global_migration_test(excel_path, n_agents=10, self_speed=100.0, start_lat=0.0, start_lon=0.0):
    """
    运行全球迁移测试

    参数:
        excel_path: 地图文件路径
        n_agents: Agent数量
        self_speed: Agent速度
        start_lat: 起始纬度
        start_lon: 起始经度
    """
    global SIMULATION_RUNNING, PREFERRED_DIRECTION

    print("=" * 60)
    print("Global Migration Function Test")
    print("=" * 60)
    print(f"Map file: {excel_path}")
    print(f"Agent count: {n_agents}")
    print(f"Agent speed: {self_speed} m/s")
    print(f"Starting position: Latitude={start_lat}, Longitude={start_lon}")
    print(f"Global simulation enabled: Yes")
    print(f"Supply limit: None (unlimited time)")
    print(f"Lifespan limit: None")
    print(f"New rule: Agents avoid land (Y) cells")
    print("=" * 60)

    # 加载地图
    try:
        grid = load_map(excel_path)
        nrows, ncols = grid.shape
        print(f"Map dimensions: {nrows}×{ncols}")
    except Exception as e:
        print(f"Failed to load map: {e}")
        return None

    # 经纬度分割
    lats_inc = np.linspace(MIN_LAT, MAX_LAT, nrows + 1)
    lons_inc = np.linspace(MIN_LON, MAX_LON, ncols + 1)

    # 创建Agents
    agents = [GlobalTestAgent(start_lat, start_lon, i, self_speed) for i in range(n_agents)]

    # 设置图形界面
    plt.ion()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # 绘制基础地图
    grid_img = np.zeros((nrows, ncols))
    for i in range(nrows):
        for j in range(ncols):
            t = grid[i, j].cell_type
            grid_img[i, j] = 0 if t == "B" else (1 if t == "G" else 2)
    cmap = ListedColormap([[0.2, 0.4, 0.8], [0.6, 0.9, 0.9], [0.25, 0.25, 0.25]])

    ax1.imshow(grid_img, cmap=cmap, origin="upper",
               extent=[MIN_LON, MAX_LON, MIN_LAT, MAX_LAT],
               interpolation="nearest", aspect="auto")

    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")
    ax1.set_title("Global Migration Simulation (Map View)")
    ax1.grid(True, alpha=0.3)

    # 第二个图：统计信息
    ax2.axis('off')
    stats_text = ax2.text(0.05, 0.95, "", transform=ax2.transAxes,
                          fontsize=10, verticalalignment='top',
                          bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    fig.canvas.manager.set_window_title("Global Migration Function Test")
    fig.tight_layout()

    # 模拟主循环
    step_count = 0
    SIMULATION_RUNNING = True

    print("\nSimulation started! Press Ctrl+C to stop...")
    print("=" * 60)

    try:
        while SIMULATION_RUNNING:
            step_count += 1

            # 更新每个Agent
            for agent in agents:
                if agent.alive:
                    agent.step(grid, lats_inc, lons_inc, PREFERRED_DIRECTION)

            # 每100步更新一次图形
            if step_count % 100 == 0:
                # 清空并重新绘制
                ax1.clear()
                ax1.imshow(grid_img, cmap=cmap, origin="upper",
                           extent=[MIN_LON, MAX_LON, MIN_LAT, MAX_LAT],
                           interpolation="nearest", aspect="auto")
                ax1.set_xlabel("Longitude")
                ax1.set_ylabel("Latitude")
                ax1.set_title(f"Global Migration Simulation (Step: {step_count})")
                ax1.grid(True, alpha=0.3)

                # 绘制所有Agent的路径
                for agent in agents:
                    if hasattr(agent, 'global_path_manager'):
                        paths = agent.global_path_manager.get_paths_for_plotting()
                        for path_lons, path_lats in paths:
                            if len(path_lons) > 1:
                                # 根据Agent状态选择颜色
                                if agent.alive:
                                    color = 'green'
                                else:
                                    color = 'red'
                                ax1.plot(path_lons, path_lats, color=color, linewidth=0.5, alpha=0.7)

                # 绘制当前Agent位置（带有数值代号的圆形标记）
                for agent in agents:
                    if agent.alive:
                        # 计算合适的圆形大小（根据经纬度坐标系统调整）
                        # 将圆形大小增大30%（2.0 * 1.3 = 2.6）
                        circle_radius = 2.6  # 经纬度单位的半径
                        # 绘制白色圆形背景，黑色边框以增强显示效果
                        circle = plt.Circle((agent.lon, agent.lat), circle_radius, 
                                           facecolor='white', edgecolor='black', linewidth=1.5, alpha=1.0)
                        ax1.add_patch(circle)
                        # 在圆形中央显示agent ID（从1开始计数），文字颜色改为红色
                        ax1.text(agent.lon, agent.lat, str(agent.agent_id + 1), 
                                color='red', fontsize=9, ha='center', va='center', 
                                bbox=dict(facecolor='none', edgecolor='none'))

                # 更新统计信息
                alive_count = sum(1 for a in agents if a.alive)
                dead_count = n_agents - alive_count

                # 计算平均距离和边界穿越次数
                avg_distance = sum(a.total_distance for a in agents) / n_agents / 1000.0
                total_boundary_crossings = sum(a.boundary_crossings for a in agents)
                total_pole_crossings = sum(a.pole_crossings for a in agents)
                total_invalid_attempts = sum(a.total_invalid_attempts for a in agents)

                # 当前偏好方向信息
                if PREFERRED_DIRECTION:
                    dir_info = f"Preferred direction: {PREFERRED_DIRECTION} (70% probability)"
                    range_start, range_end = DIRECTION_RANGES[PREFERRED_DIRECTION]
                    dir_info += f"\nDirection range: {range_start}° to {range_end}°"
                else:
                    dir_info = "Preferred direction: None (completely random)"

                stats = f"""Simulation Statistics:
Step: {step_count}
Alive Agents: {alive_count} / {n_agents}
Dead Agents: {dead_count}

Movement Statistics:
Average distance: {avg_distance:.2f} km
Boundary crossings: {total_boundary_crossings}
Pole crossings: {total_pole_crossings}
Invalid move attempts: {total_invalid_attempts}

{dir_info}

Control Instructions:
Click direction buttons to set preferred direction
Click 'Random Direction' to remove preference
Click 'Stop Simulation' to end test
"""
                stats_text.set_text(stats)

                # 刷新图形
                fig.canvas.draw_idle()
                fig.canvas.flush_events()

                # 输出进度信息
                print(
                    f"Step: {step_count}, Alive: {alive_count}, Avg distance: {avg_distance:.1f}km, Invalid attempts: {total_invalid_attempts}",
                    end='\r')

                # 如果所有Agent都死亡，停止模拟
                if alive_count == 0:
                    print("\nAll agents have died, simulation ended.")
                    SIMULATION_RUNNING = False
                    break

    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user.")
    except Exception as e:
        print(f"\nSimulation error: {e}")
    finally:
        SIMULATION_RUNNING = False
        plt.ioff()

        # 显示最终结果
        print("\n" + "=" * 60)
        print("Simulation Results:")
        print("=" * 60)

        for i, agent in enumerate(agents):
            stats = agent.get_stats()
            print(f"Agent {i + 1}:")
            print(f"  Status: {'Alive' if stats['alive'] else 'Dead'} ({stats['death_type']})")
            print(f"  Position: Latitude={stats['current_lat']:.4f}, Longitude={stats['current_lon']:.4f}")
            print(f"  Distance traveled: {stats['total_distance_km']:.2f} km")
            print(f"  Boundary crossings: {stats['boundary_crossings']} times")
            print(f"  Pole crossings: {stats['pole_crossings']} times")
            print(f"  Invalid move attempts: {stats['total_invalid_attempts']} times")
            print(f"  Last direction: {stats['last_direction']} ({stats['last_angle']:.1f}°)")
            print()

        return agents


def create_test_ui():
    """创建测试用户界面"""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    global SIMULATION_RUNNING, PREFERRED_DIRECTION

    # 主窗口
    root = tk.Tk()
    root.title("Global Migration Function Test")
    root.geometry("500x850")

    # 标题
    title_label = tk.Label(root, text="Global Migration Function Test", font=("Arial", 16, "bold"))
    title_label.pack(pady=10)

    # 说明文本
    info_text = """Function Description:
1. Test global migration function (crossing longitude/latitude boundaries)
2. Agents have no supply limit, unlimited time to move
3. Can set preferred movement direction (40% probability)
4. Real-time display of migration paths and statistics
5. New rule: Agents avoid land cells (Y) - they will retry with new step time and direction
6. Program runs until manually stopped"""

    info_label = tk.Label(root, text=info_text, justify=tk.LEFT, font=("Arial", 10))
    info_label.pack(pady=10, padx=20)

    # 分隔线
    ttk.Separator(root, orient='horizontal').pack(fill='x', padx=20, pady=10)

    # 地图文件选择
    map_frame = ttk.LabelFrame(root, text="Map File Selection", padding=10)
    map_frame.pack(fill='x', padx=20, pady=5)

    map_path_var = tk.StringVar(value="merged_result.xlsx")

    def browse_map_file():
        file_path = filedialog.askopenfilename(
            title="Select Map Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if file_path:
            map_path_var.set(file_path)

    ttk.Entry(map_frame, textvariable=map_path_var, width=40).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(map_frame, text="Browse", command=browse_map_file).pack(side=tk.LEFT)

    # 参数设置
    param_frame = ttk.LabelFrame(root, text="Simulation Parameters", padding=10)
    param_frame.pack(fill='x', padx=20, pady=5)

    # Agent数量
    ttk.Label(param_frame, text="Agent count:").grid(row=0, column=0, sticky=tk.W, pady=5)
    agents_var = tk.IntVar(value=10)
    ttk.Spinbox(param_frame, from_=1, to=100, textvariable=agents_var, width=10).grid(row=0, column=1, sticky=tk.W,
                                                                                      pady=5)

    # Agent速度
    ttk.Label(param_frame, text="Agent speed (m/s):").grid(row=1, column=0, sticky=tk.W, pady=5)
    speed_var = tk.DoubleVar(value=100.0)
    ttk.Spinbox(param_frame, from_=10, to=500, increment=10, textvariable=speed_var, width=10).grid(row=1, column=1,
                                                                                                    sticky=tk.W, pady=5)

    # 起始位置
    ttk.Label(param_frame, text="Starting latitude:").grid(row=2, column=0, sticky=tk.W, pady=5)
    lat_var = tk.DoubleVar(value=0.0)
    ttk.Spinbox(param_frame, from_=-90, to=90, increment=5, textvariable=lat_var, width=10).grid(row=2, column=1,
                                                                                                 sticky=tk.W, pady=5)

    ttk.Label(param_frame, text="Starting longitude:").grid(row=3, column=0, sticky=tk.W, pady=5)
    lon_var = tk.DoubleVar(value=0.0)
    ttk.Spinbox(param_frame, from_=-180, to=180, increment=10, textvariable=lon_var, width=10).grid(row=3, column=1,
                                                                                                    sticky=tk.W, pady=5)

    # 方向选择区域
    direction_frame = ttk.LabelFrame(root, text="Preferred Direction Setting (Click to select)", padding=15)
    direction_frame.pack(fill='both', expand=True, padx=20, pady=10)

    # 方向按钮
    def set_preferred_direction(direction):
        global PREFERRED_DIRECTION
        PREFERRED_DIRECTION = direction

        # 更新按钮状态
        for btn_dir, btn in direction_buttons.items():
            if btn_dir == direction:
                btn.config(relief='sunken', bg='lightblue')
            else:
                btn.config(relief='raised', bg='SystemButtonFace')

        print(f"Preferred direction set: {direction}")

    def set_random_direction():
        global PREFERRED_DIRECTION
        PREFERRED_DIRECTION = None

        # 重置所有按钮
        for btn in direction_buttons.values():
            btn.config(relief='raised', bg='SystemButtonFace')

        print("Preferred direction removed (random movement)")

    # 创建方向按钮布局
    button_frame = tk.Frame(direction_frame)
    button_frame.pack(expand=True)

    direction_buttons = {}

    # 北按钮
    btn_n = tk.Button(button_frame, text="North\n(315°-45°)", width=8, height=3,
                      command=lambda: set_preferred_direction('N'))
    btn_n.grid(row=0, column=1, padx=5, pady=5)
    direction_buttons['N'] = btn_n

    # 西按钮
    btn_w = tk.Button(button_frame, text="West\n(225°-315°)", width=8, height=3,
                      command=lambda: set_preferred_direction('W'))
    btn_w.grid(row=1, column=0, padx=5, pady=5)
    direction_buttons['W'] = btn_w

    # 随机按钮
    btn_random = tk.Button(button_frame, text="Random\nDirection", width=8, height=3,
                           command=set_random_direction, bg='lightyellow')
    btn_random.grid(row=1, column=1, padx=5, pady=5)

    # 东按钮
    btn_e = tk.Button(button_frame, text="East\n(45°-135°)", width=8, height=3,
                      command=lambda: set_preferred_direction('E'))
    btn_e.grid(row=1, column=2, padx=5, pady=5)
    direction_buttons['E'] = btn_e

    # 南按钮
    btn_s = tk.Button(button_frame, text="South\n(135°-225°)", width=8, height=3,
                      command=lambda: set_preferred_direction('S'))
    btn_s.grid(row=2, column=1, padx=5, pady=5)
    direction_buttons['S'] = btn_s

    # 控制按钮
    control_frame = tk.Frame(root)
    control_frame.pack(pady=15)

    def start_simulation():
        """开始模拟"""
        global SIMULATION_RUNNING

        map_path = map_path_var.get()
        if not map_path or not Path(map_path).exists():
            messagebox.showerror("Error", "Please select a valid map file")
            return

        # 关闭UI窗口
        root.withdraw()

        # 在新线程中运行模拟（避免阻塞UI）
        def run_sim_thread():
            run_global_migration_test(
                excel_path=map_path,
                n_agents=agents_var.get(),
                self_speed=speed_var.get(),
                start_lat=lat_var.get(),
                start_lon=lon_var.get()
            )
            # 模拟结束后恢复窗口
            root.deiconify()

        sim_thread = threading.Thread(target=run_sim_thread, daemon=True)
        sim_thread.start()

    def stop_simulation():
        """停止模拟"""
        global SIMULATION_RUNNING
        SIMULATION_RUNNING = False
        messagebox.showinfo("Info", "Stop signal sent. Simulation will stop at next check.")

    def on_closing():
        """窗口关闭事件"""
        global SIMULATION_RUNNING
        SIMULATION_RUNNING = False
        root.destroy()

    ttk.Button(control_frame, text="Start Simulation", command=start_simulation,
               style="Accent.TButton").pack(side=tk.LEFT, padx=5)
    ttk.Button(control_frame, text="Stop Simulation", command=stop_simulation).pack(side=tk.LEFT, padx=5)
    ttk.Button(control_frame, text="Exit", command=on_closing).pack(side=tk.LEFT, padx=5)

    # 状态标签
    status_label = tk.Label(root, text="Ready", fg="green", font=("Arial", 10))
    status_label.pack(pady=5)

    def update_status():
        """更新状态标签"""
        if SIMULATION_RUNNING:
            status_label.config(text="Simulation running...", fg="blue")
        else:
            status_label.config(text="Ready", fg="green")
        root.after(1000, update_status)

    # 设置窗口关闭事件
    root.protocol("WM_DELETE_WINDOW", on_closing)

    # 开始状态更新
    update_status()

    # 运行主循环
    root.mainloop()


if __name__ == "__main__":
    print("Global Migration Function Test Script")
    print("=" * 60)

    # 检查必要的模块
    if not GLOBAL_SIM_AVAILABLE:
        print("Warning: Global simulation functions may not be available")
        print("Please ensure the following modules are correctly installed:")
        print("1. simulation_utils.py")
        print("2. global_simulation_utils.py")
        print("3. simulation_constants.py")
        print("=" * 60)

    # 启动测试UI
    create_test_ui()