from __future__ import annotations
import math
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import tkinter as tk
from typing import List, Tuple, Optional
# 导入全局常量
from simulation_constants import *

# ------------------------------------------------------------------------------
# 配置文件相关
# ------------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).resolve().parent / "simulation_config.json"


def load_max_migration_seconds(days):
    """动态计算满状态生存时间（天→秒）"""
    return days * 24 * 3600


def load_config():
    """读取配置文件"""
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 补全缺失的配置项
        for key, default_val in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = default_val
        return config
    except (json.JSONDecodeError, PermissionError):
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except PermissionError:
        from tkinter import messagebox
        messagebox.showwarning("配置保存警告", "无权限写入配置文件，下次启动将使用默认设置")


# ------------------------------------------------------------------------------
# 辅助判断函数
# ------------------------------------------------------------------------------
def is_angle_disabled(angle: float, disabled_directions: dict) -> bool:
    """判断角度是否在禁用方向"""
    a = angle % 360

    # 定义临近方向组合
    adjacent_pairs = [("N", "E"), ("E", "S"), ("S", "W"), ("W", "N")]

    # 1. 优先判断临近方向组合是否同时禁用
    for dir1, dir2 in adjacent_pairs:
        if disabled_directions[dir1] and disabled_directions[dir2]:
            if (dir1, dir2) == ("N", "E") or (dir1, dir2) == ("E", "N"):
                if a >= 271 or a <= 179:
                    return True
            elif (dir1, dir2) == ("E", "S") or (dir1, dir2) == ("S", "E"):
                if 1 <= a <= 269:
                    return True
            elif (dir1, dir2) == ("S", "W") or (dir1, dir2) == ("W", "S"):
                if 91 <= a <= 359:
                    return True
            elif (dir1, dir2) == ("W", "N") or (dir1, dir2) == ("N", "W"):
                if a >= 181 or a <= 89:
                    return True

    # 2. 判断单个方向是否禁用
    if disabled_directions["N"] and (a >= 271 or a <= 89):
        return True
    if disabled_directions["E"] and (1 <= a <= 179):
        return True
    if disabled_directions["S"] and (91 <= a <= 269):
        return True
    if disabled_directions["W"] and (181 <= a <= 359):
        return True

    return False


def temperature_to_score(temp: float) -> float:
    """温度转换为对应分数"""
    for tmin, tmax, score in TEMP_SCORE:
        if tmin <= temp < tmax:
            return score
    return 0.0


# ------------------------------------------------------------------------------
# 工具类函数
# ------------------------------------------------------------------------------
def bresenham_line(x0, y0, x1, y1):
    """Bresenham直线算法"""
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return points


def get_grid_index(lat, lon, lats_inc, lons_inc, nrows, enable_global_simulation: bool = False):
    """将经纬度转换为网格索引[i, j]"""
    # 在全球模拟模式下，确保坐标在地图范围内
    if enable_global_simulation:
        lat = max(MIN_LAT, min(MAX_LAT, lat))
        lon = max(MIN_LON, min(MAX_LON, lon))

    i_band = int(np.searchsorted(lats_inc, lat, side="right") - 1)
    j_band = int(np.searchsorted(lons_inc, lon, side="right") - 1)
    i_row = nrows - 1 - i_band

    # 边界检查
    if i_row < 0 or i_row >= nrows or j_band < 0 or j_band >= len(lons_inc) - 1:
        if enable_global_simulation:
            i_row = max(0, min(nrows - 1, i_row))
            j_band = max(0, min(len(lons_inc) - 2, j_band))
            return i_row, j_band
        return None
    return i_row, j_band


def locate_cell(lat: float, lon: float, grid: np.ndarray, lats_inc: np.ndarray, lons_inc: np.ndarray,
                enable_global_simulation: bool = False):
    """经纬度定位网格单元"""
    nrows, ncols = grid.shape

    # 在全球模拟模式下，确保坐标在地图范围内
    if enable_global_simulation:
        lat = max(MIN_LAT, min(MAX_LAT, lat))
        lon = max(MIN_LON, min(MAX_LON, lon))

    i_band = int(np.searchsorted(lats_inc, lat, side="right") - 1)
    j_band = int(np.searchsorted(lons_inc, lon, side="right") - 1)
    i_row = nrows - 1 - i_band

    if 0 <= i_row < nrows and 0 <= j_band < ncols:
        return grid[i_row, j_band]

    # 在全球模拟模式下，如果坐标超出范围，尝试找到最近的单元格
    if enable_global_simulation:
        i_row = max(0, min(nrows - 1, i_row))
        j_band = max(0, min(ncols - 1, j_band))
        return grid[i_row, j_band]

    return None


def haversine_distance(lat1, lon1, lat2, lon2) -> float:
    """计算两点经纬度之间的直线距离（米）"""
    R = 6371000
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def default_excel_path() -> Path:
    """获取默认的Excel文件路径"""
    script_dir = Path(__file__).resolve().parent
    p1 = script_dir / "merged_result.xlsx"
    if p1.exists():
        return p1
    return Path.cwd() / "merged_result.xlsx"


# ------------------------------------------------------------------------------
# 地图与单元格处理
# ------------------------------------------------------------------------------
class GridCell:
    """网格单元格类"""

    def __init__(self, cell_type: str, current_dir: float | None = None):
        self.cell_type = cell_type
        self.current_dir = current_dir

    def current_vector(self) -> tuple[float, float]:
        """计算洋流的东西、南北方向分量"""
        if self.current_dir is None:
            return 0.0, 0.0
        ang = math.radians(self.current_dir)
        east = CURRENT_SPEED * math.sin(ang)
        north = CURRENT_SPEED * math.cos(ang)
        return east, north


def parse_cell(val) -> GridCell:
    """解析Excel单元格值，转换为GridCell实例"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return GridCell("B")

    s = str(val).strip()
    if s in {"G", "Y", "B"}:
        return GridCell(s)

    if "-" in s:
        ang_part, type_part = s.split("-", 1)
        try:
            ang = float(ang_part)
        except ValueError:
            ang = None
        t = type_part.strip().upper()
        if t not in {"G", "B", "Y"}:
            t = "B"
        return GridCell(t, ang)

    return GridCell("B")


def load_map(excel_path: str) -> np.ndarray:
    """加载Excel地图文件，返回GridCell类型的网格数组"""
    df = pd.read_excel(excel_path, header=None)
    nrows, ncols = df.shape

    if (nrows, ncols) == (224, 288):
        print("[Map Type] Detected Simple Map (224×288)")
    elif (nrows, ncols) == (180, 360):
        print("[Map Type] Detected Global Map (180×360)")
    else:
        print(f"[Warning] Unrecognized map resolution ({nrows}×{ncols}), treated as custom map.")

    grid = np.empty((nrows, ncols), dtype=object)
    for i in range(nrows):
        for j in range(ncols):
            grid[i, j] = parse_cell(df.iat[i, j])
    return grid


# ------------------------------------------------------------------------------
# 导出与交互模块
# ------------------------------------------------------------------------------
def export_png(agents, parent_window):
    """导出Agent迁移路径为透明PNG图片"""
    alive_color = "#00ff00"
    color_tuple = colorchooser.askcolor(
        title="Select Color for Alive Agents",
        color=alive_color,
        parent=parent_window
    )
    if color_tuple and color_tuple[1]:
        alive_color = color_tuple[1]

    fig_width = 12
    fig_height = 6
    export_fig, export_ax = plt.subplots(figsize=(fig_width, fig_height))
    export_ax.set_facecolor("none")
    export_ax.axis("off")

    # 导入全球模拟工具（如果可用）
    try:
        from global_simulation_utils import plot_global_paths
        GLOBAL_SIM_AVAILABLE = True
    except ImportError:
        GLOBAL_SIM_AVAILABLE = False

    # 创建颜色映射
    color_map = {}
    for i, ag in enumerate(agents):
        if ag.alive:
            color = alive_color
        elif ag.death_type == "lifespan":
            color = "#ff7f0e"
        elif ag.death_type == "supply":
            color = "#ff0000"
        else:
            color = "#888888"
        color_map[i] = color

    # 优先使用全球模拟路径（如果可用）
    global_paths_used = False
    if GLOBAL_SIM_AVAILABLE:
        try:
            plot_global_paths(export_ax, agents, color_map)
            global_paths_used = True
        except Exception as e:
            print(f"全球路径导出错误: {e}")

    # 只有在非全球模拟模式下才使用普通路径
    # 全球模拟模式下不使用self.path绘制（避免跨经线直线问题）
    if not GLOBAL_SIM_AVAILABLE and not global_paths_used:
        for ag in agents:
            if hasattr(ag, 'path') and len(ag.path) > 1:
                ys, xs = zip(*ag.path)
                if ag.alive:
                    color = alive_color
                elif ag.death_type == "lifespan":
                    color = "#ff7f0e"
                elif ag.death_type == "supply":
                    color = "#ff0000"
                else:
                    color = "#888888"
                export_ax.plot(xs, ys, color=color, linewidth=0.5, alpha=0.9)

    export_ax.set_xlim(MIN_LON, MAX_LON)
    export_ax.set_ylim(MIN_LAT, MAX_LAT)
    export_ax.set_aspect('equal', adjustable='box')

    save_path = filedialog.asksaveasfilename(
        title="Export Levy Migration Paths",
        defaultextension=".png",
        filetypes=[("PNG Image", "*.png")],
        parent=parent_window
    )

    if save_path:
        export_fig.savefig(
            save_path,
            dpi=300,
            transparent=True,
            bbox_inches='tight',
            pad_inches=0
        )
        plt.close(export_fig)
        messagebox.showinfo(
            "Export Completed",
            f"Levy paths saved to:\n{save_path}\n\nAlive agents color: {alive_color}",
            parent=parent_window
        )
    else:
        plt.close(export_fig)


def export_agent_data(agents, parent_window, direction_seed: int = None, levy_seed: int = None, levy_exp: float = None):
    """导出Agent数据到XLSX"""
    save_path = filedialog.asksaveasfilename(
        title="Export Agent Data",
        defaultextension=".xlsx",
        filetypes=[("Excel File", "*.xlsx")],
        parent=parent_window
    )
    if not save_path:
        return

    agent_data = []
    total_time = 0.0
    total_distance = 0.0
    valid_agents = 0

    for idx, ag in enumerate(agents, 1):
        distance = haversine_distance(start_lat, start_lon, ag.lat, ag.lon)
        alive_status = "存活" if ag.alive else "死亡"
        death_reason = ag.death_type if ag.death_type else "无"
        agent_detail = {
            "Agent编号": idx,
            "存活状态": alive_status,
            "死亡原因": death_reason,
            "步进总耗时（秒）": round(ag.total_alive_seconds, 4),
            "直线迁移距离（米）": round(distance, 4)
        }
        agent_data.append(agent_detail)

        if len(ag.path) > 1 and ag.total_alive_seconds >= 0 and distance >= 0:
            total_time += ag.total_alive_seconds
            total_distance += distance
            valid_agents += 1

    avg_time = round(total_time / valid_agents, 4) if valid_agents > 0 else 0.0
    avg_distance = round(total_distance / valid_agents, 4) if valid_agents > 0 else 0.0

    with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
        df_detail = pd.DataFrame(agent_data)
        df_detail.to_excel(writer, sheet_name="Agent详细数据", index=False)

        summary_data = {
            "统计项": [
                "有效Agent总数",
                "所有Agent总耗时（秒）",
                "所有Agent总迁移距离（米）",
                "平均步进耗时（秒/Agent）",
                "平均迁移距离（米/Agent）",
                "方向种子（Direction Seed）",
                "Levy种子（Levy Seed）",
                "LEVY_EXP数值",
            ],
            "数值": [
                valid_agents,
                round(total_time, 4),
                round(total_distance, 4),
                avg_time,
                avg_distance,
                direction_seed,
                levy_seed,
                levy_exp if levy_exp is not None else LEVY_EXP_PRIMARY,
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name="统计汇总", index=False)

    messagebox.showinfo(
        "Export Completed",
        f"Agent数据已保存到：\n{save_path}\n\n"
        f"统计汇总：\n"
        f"有效Agent总数：{valid_agents}\n"
        f"平均步进耗时：{avg_time} 秒\n"
        f"平均迁移距离：{avg_distance} 米\n"
        f"方向种子：{direction_seed}\n"
        f"Levy种子：{levy_seed}\n\n"
        f"Excel包含2个工作表：\n"
        f"1. Agent详细数据（单个Agent信息）\n"
        f"2. 统计汇总（平均值+种子信息）",
        parent=parent_window
    )


def show_interactive_window(fig, agents, actual_steps: int, max_steps: int,
                            direction_seed: int = None, levy_seed: int = None,
                            levy_exp: float = None):
    """创建交互窗口"""
    alive_count = sum(1 for a in agents if a.alive)
    total_agents = len(agents)
    lifespan_death_count = sum(1 for a in agents if not a.alive and a.death_type == "lifespan")
    supply_death_count = sum(1 for a in agents if not a.alive and a.death_type == "supply")
    bounds_death_count = sum(1 for a in agents if not a.alive and a.death_type == "out_of_bounds")

    root = tk.Tk()
    if actual_steps < max_steps:
        root.title(f"Levy Simulation Results (Early Terminated) - View & Export")
    else:
        root.title("Levy Simulation Results - View & Export")
    root.geometry("1500x800")

    def on_closing():
        try:
            plt.close(fig)
        except:
            pass
        root.destroy()
        import gc
        gc.collect()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    left_frame = ttk.Frame(root)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

    canvas = FigureCanvasTkAgg(fig, master=left_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    toolbar = NavigationToolbar2Tk(canvas, left_frame)
    toolbar.update()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    right_frame = ttk.Frame(root)
    right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

    export_btn = ttk.Button(
        right_frame,
        text="Export PNG Image",
        command=lambda: export_png(agents, root),
        width=20
    )
    export_btn.pack(pady=20, ipady=5)

    export_data_btn = ttk.Button(
        right_frame,
        text="Export Agent Data (XLSX)",
        command=lambda: export_agent_data(agents, root, direction_seed, levy_seed, levy_exp),
        width=20
    )
    export_data_btn.pack(pady=10, ipady=5)

    close_btn = ttk.Button(
        right_frame,
        text="Close Window",
        command=on_closing,
        width=20
    )
    close_btn.pack(pady=10, ipady=5)

    steps_info = f"Steps: {actual_steps}/{max_steps}"
    if actual_steps < max_steps:
        steps_info += " (All agents died)"

    stats_text = f"Statistics:\n{steps_info}\nTotal Agents: {total_agents}\nAlive Agents: {alive_count}\n" \
                 f"Lifespan Deaths: {lifespan_death_count}\nSupply Deaths: {supply_death_count}\n" \
                 f"Bounds Deaths: {bounds_death_count}\nCurrent Mode: {current_influence_mode}\n" \
                 f"Direction Mode: {direction_mode}\nLifespan Limit: {'Enabled' if ENABLE_LIFESPAN_LIMIT else 'Disabled'}\n" \
                 f"Direction Seed: {direction_seed}\nLevy Seed: {levy_seed}\n" \
                 f"Current LEVY_EXP: {levy_exp}"

    stats_label = ttk.Label(
        right_frame,
        text=stats_text,
        justify=tk.LEFT
    )
    stats_label.pack(pady=30, padx=10)

    def check_close():
        try:
            root.update()
            if root.winfo_exists():
                root.after(100, check_close)
            else:
                on_closing()
        except:
            pass

    root.after(100, check_close)
    root.update()

    print("交互窗口已显示，关闭后将自动继续...")
    root.mainloop()