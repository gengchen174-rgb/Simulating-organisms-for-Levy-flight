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
def export_png(agents, parent_window, export_prefix="simulation"):
    """导出Agent迁移路径为透明PNG图片"""
    alive_color = "#00ff00"
    
    # 如果没有父窗口（自动模式），直接使用默认颜色，否则显示颜色选择器
    if parent_window:
        color_tuple = colorchooser.askcolor(
            title="Select Color for Alive Agents",
            color=alive_color,
            parent=parent_window
        )
        if color_tuple and color_tuple[1]:
            alive_color = color_tuple[1]

    # 在后台线程中安全使用Matplotlib
    import matplotlib
    
    # 设置Matplotlib为非交互模式，避免GUI线程问题
    matplotlib.use('Agg')  # 使用非GUI后端
    
    # 重新导入plt以确保使用正确的后端
    import matplotlib.pyplot as plt
    
    fig_width = 12
    fig_height = 6
    
    # 创建图形时设置dpi和避免GUI警告
    plt.ioff()  # 关闭交互模式
    export_fig, export_ax = plt.subplots(figsize=(fig_width, fig_height), dpi=100)
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
    
    # 检查是否有Agent启用了全球模拟
    any_agent_global_enabled = any(hasattr(ag, 'enable_global_simulation') and ag.enable_global_simulation for ag in agents)
    
    if GLOBAL_SIM_AVAILABLE and any_agent_global_enabled:
        try:
            plot_global_paths(export_ax, agents, color_map)
            global_paths_used = True
            print("✅ 使用全球模式路径绘制")
        except Exception as e:
            print(f"全球路径导出错误: {e}")
    else:
        print(f"全球路径绘制条件: GLOBAL_SIM_AVAILABLE={GLOBAL_SIM_AVAILABLE}, any_agent_global_enabled={any_agent_global_enabled}")

    # 在全球模拟模式下，如果全球路径绘制失败，或者非全球模拟模式下，使用普通路径
    # 修复：移除对GLOBAL_SIM_AVAILABLE的限制，确保所有情况下都能绘制路径
    if not global_paths_used:
        print("使用非全球模式路径绘制...")
        agents_with_path = 0
        total_path_points = 0
        
        for ag in agents:
            if hasattr(ag, 'path') and len(ag.path) > 1:
                agents_with_path += 1
                total_path_points += len(ag.path)
                
                try:
                    # 调试：打印路径信息
                    print(f"绘制Agent路径，点数量: {len(ag.path)}")
                    
                    # 确保路径点格式正确
                    if len(ag.path[0]) != 2:
                        print(f"⚠️ 路径点格式错误: {ag.path[0]}")
                        continue
                    
                    ys, xs = zip(*ag.path)
                    
                    # 调试：检查坐标范围
                    print(f"  经度范围: {min(xs):.2f} ~ {max(xs):.2f}")
                    print(f"  纬度范围: {min(ys):.2f} ~ {max(ys):.2f}")
                    
                    # 设置颜色
                    if ag.alive:
                        color = alive_color
                        print(f"  颜色: 绿色 (存活)")
                    elif ag.death_type == "lifespan":
                        color = "#ff7f0e"
                        print(f"  颜色: 橙色 (寿命耗尽)")
                    elif ag.death_type == "supply":
                        color = "#ff0000"
                        print(f"  颜色: 红色 (补给耗尽)")
                    else:
                        color = "#888888"
                        print(f"  颜色: 灰色 (其他)")
                    
                    # 绘制路径 - 增加线宽和透明度以便观察
                    export_ax.plot(xs, ys, color=color, linewidth=1.0, alpha=0.9)
                    print("  ✅ 路径绘制成功")
                    
                except Exception as e:
                    print(f"  ❌ 路径绘制失败: {e}")
                    import traceback
                    traceback.print_exc()
        
        print(f"非全球模式路径绘制完成: {agents_with_path}个Agent有路径，总路径点: {total_path_points}")
    else:
        print("使用全球模式路径绘制")

    export_ax.set_xlim(MIN_LON, MAX_LON)
    export_ax.set_ylim(MIN_LAT, MAX_LAT)
    export_ax.set_aspect('equal', adjustable='box')

    # 确保result文件夹存在（使用程序文件所在目录，而不是当前工作目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    result_dir = os.path.join(script_dir, "result")
    os.makedirs(result_dir, exist_ok=True)
    
    # 自动模式：直接使用前缀生成文件名，否则显示保存对话框
    if not parent_window:
        # 自动命名模式，保存到result文件夹
        save_path = os.path.join(result_dir, f"{export_prefix}.png")
    else:
        # 交互式模式，默认保存到result文件夹
        save_path = filedialog.asksaveasfilename(
            title="Export Levy Migration Paths",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            parent=parent_window,
            initialdir=result_dir
        )

    if save_path:
        # 添加智能等待机制，确保所有Levy路线绘制完成
        # 基于渲染复杂度动态调整等待时间
        import time
        import math
        
        # 计算需要绘制的路径总数
        total_paths = sum(1 for ag in agents if hasattr(ag, 'path') and len(ag.path) > 1)
        
        # 计算总步数和平均路径长度
        total_steps = 0
        valid_agents = 0
        for ag in agents:
            if hasattr(ag, 'path') and len(ag.path) > 1:
                total_steps += len(ag.path)
                valid_agents += 1
        
        avg_steps_per_path = total_steps / max(valid_agents, 1) if valid_agents > 0 else 0
        
        # 智能计算等待时间：基于渲染复杂度
        # 基础等待时间（最小等待）
        base_wait_time = 0.3  # 进一步减少基础等待时间
        
        # 计算渲染复杂度（路径数 × 平均步数）
        render_complexity = total_paths * avg_steps_per_path
        
        # 根据计算量动态调整等待时间
        # 基准：200 agents × 100,000 steps = 20,000,000 复杂度需要60秒
        if render_complexity <= 1000:  # 非常小的实验（10路径×100步）
            wait_time = 0.1
        elif render_complexity <= 5000:  # 小实验（25路径×200步）
            wait_time = 0.3
        elif render_complexity <= 20000:  # 较小实验（50路径×400步）
            wait_time = 0.5
        elif render_complexity <= 50000:  # 中等实验（100路径×500步）
            wait_time = 1.0
        elif render_complexity <= 100000:  # 中等偏大实验（200路径×500步）
            wait_time = 1.5
        elif render_complexity <= 500000:  # 较大实验（200路径×2500步）
            wait_time = 3.0
        elif render_complexity <= 1000000:  # 大实验（200路径×5000步）
            wait_time = 5.0
        elif render_complexity <= 2000000:  # 较大实验（200路径×10000步）
            wait_time = 10.0
        elif render_complexity <= 5000000:  # 很大实验（200路径×25000步）
            wait_time = 15.0
        elif render_complexity <= 10000000:  # 极大实验（200路径×50000步）
            wait_time = 30.0
        elif render_complexity <= 20000000:  # 超极大实验（200路径×100000步）
            wait_time = 60.0
        else:  # 极端规模实验
            wait_time = 90.0
        
        # 确保等待时间不低于基础值
        wait_time = max(wait_time, base_wait_time)
        
        print(f"正在等待渲染完成... 预计等待时间: {wait_time:.1f}秒 (路径数: {total_paths}, 平均步数: {avg_steps_per_path:.0f}, 复杂度: {render_complexity:.0f})")
        
        # 强制刷新画布并等待
        if hasattr(export_fig, 'canvas'):
            export_fig.canvas.draw_idle()
        
        # 等待渲染完成
        time.sleep(wait_time)
        
        # 再次强制刷新确保所有路径都已渲染
        if hasattr(export_fig, 'canvas'):
            export_fig.canvas.draw_idle()
            time.sleep(0.5)  # 额外等待0.5秒
        
        # 保存图片（使用try-except确保异常不会中断程序）
        try:
            export_fig.savefig(
                save_path,
                dpi=300,
                transparent=True,
                bbox_inches='tight',
                pad_inches=0
            )
            print(f"PNG图片已成功导出: {save_path}")
        except Exception as e:
            print(f"PNG图片导出失败: {e}")
            # 即使导出失败，也要继续执行
        finally:
            # 确保图形资源被清理
            try:
                plt.close(export_fig)
            except:
                pass
            
            # 清理Matplotlib缓存
            try:
                plt.close('all')
            except:
                pass
        
        # 只有在交互式模式下显示消息框
        if parent_window:
            # 创建自动关闭的消息框
            def auto_close_messagebox():
                # 查找并关闭消息框窗口
                for widget in parent_window.winfo_children():
                    if widget.winfo_class() == 'Toplevel':
                        widget.destroy()
                        break
            
            # 显示消息框
            msg_box = messagebox.showinfo(
                "Export Completed",
                f"Levy paths saved to:\n{save_path}\n\nAlive agents color: {alive_color}\n\n窗口将在3秒后自动关闭...",
                parent=parent_window
            )
            
            # 3秒后自动关闭
            parent_window.after(3000, auto_close_messagebox)
    else:
        # 如果没有保存路径，也要清理图形资源
        try:
            plt.close(export_fig)
        except:
            pass


def calculate_bearing(start_lat, start_lon, end_lat, end_lon):
    """
    计算从起点到终点的方位角
    以北为0度，顺时针旋转增加角度
    """
    delta_lon = end_lon - start_lon
    delta_lat = end_lat - start_lat
    
    # 计算方位角（以北为0度，顺时针增加）
    # 使用二维坐标计算：东为x轴正方向，北为y轴正方向
    # 方位角 = arctan2(delta_lon, delta_lat) 转换为度数
    bearing = math.degrees(math.atan2(delta_lon, delta_lat))
    
    # 转换为0-360度范围（顺时针方向）
    bearing = (bearing + 360) % 360
    
    return bearing

def calculate_path_distance(path, use_fast_approx=True):
    """
    计算agent实际迁移路径的总距离（沿着弯曲路径累加）
    path: 包含(lat, lon)点的列表
    use_fast_approx: 是否使用快速近似距离计算（默认True）
    返回：总距离（米）
    """
    if path is None or len(path) < 2:
        return 0.0
    
    total_distance = 0.0
    
    # 计算所有路径点，不进行采样（避免小步进场景下丢失距离）
    for i in range(len(path) - 1):
        lat1, lon1 = path[i]
        lat2, lon2 = path[i + 1]
        
        if use_fast_approx:
            # 快速近似计算：使用经纬度差估算距离
            delta_lat = abs(lat2 - lat1)
            delta_lon = abs(lon2 - lon1)
            # 使用平均系数111公里/度进行估算
            segment_dist = math.hypot(delta_lat, delta_lon) * 111 * 1000
        else:
            # 精确计算：使用haversine公式
            segment_dist = haversine_distance(lat1, lon1, lat2, lon2)
        
        total_distance += segment_dist
    
    return total_distance


def export_agent_data(agents, parent_window, direction_seed: int = None, levy_seed: int = None, levy_exp: float = None, export_prefix="simulation",
                      start_lat=None, start_lon=None, self_speed=None, direction_mode=None, current_influence_mode=None,
                      enable_lifespan_limit=None, lifespan_years=None, pure_full_state_survival_days=None,
                      enable_b_supply=None, b_supply_percent=None, enable_global_simulation=None,
                      n_agents=None, max_steps=None, actual_steps=None, grid=None, lats_inc=None, lons_inc=None,
                      step_time_multiplier=None):
    """导出Agent数据到XLSX"""
    # 确保result文件夹存在（使用程序文件所在目录，而不是当前工作目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    result_dir = os.path.join(script_dir, "result")
    os.makedirs(result_dir, exist_ok=True)
    
    # 自动模式：直接使用前缀生成文件名，否则显示保存对话框
    if not parent_window:
        # 自动命名模式，保存到result文件夹
        save_path = os.path.join(result_dir, f"{export_prefix}.xlsx")
    else:
        # 交互式模式，默认保存到result文件夹
        save_path = filedialog.asksaveasfilename(
            title="Export Agent Data",
            defaultextension=".xlsx",
            filetypes=[("Excel File", "*.xlsx")],
            parent=parent_window,
            initialdir=result_dir
        )
    if not save_path:
        return

    agent_data = []
    total_time = 0.0
    total_distance = 0.0
    valid_agents = 0

    for idx, ag in enumerate(agents, 1):
        # 直线迁移距离（起点到终点的直线距离）
        straight_distance = haversine_distance(start_lat, start_lon, ag.lat, ag.lon)
        
        # 实际路径距离（沿着弯曲路径累加的距离）
        # 计算所有路径点（不采样，保证小步进场景下的精度），使用快速近似计算
        path_distance = calculate_path_distance(getattr(ag, 'path', None), 
                                               use_fast_approx=True)
        
        alive_status = "存活" if ag.alive else "死亡"
        death_reason = ag.death_type if ag.death_type else "无"
        
        # 确定死亡时所在区域类型（仅对死亡的agent有效）
        death_zone = "存活中"
        if not ag.alive and grid is not None and lats_inc is not None and lons_inc is not None:
            # 使用agent自身的enable_global_simulation设置，确保与模拟时一致
            agent_global_sim = getattr(ag, 'enable_global_simulation', False)
            cell = locate_cell(ag.lat, ag.lon, grid, lats_inc, lons_inc, agent_global_sim)
            if cell is not None:
                # agent不应该进入Y区域（陆地），如果检测到Y，说明是边界穿越或检测误差
                if cell.cell_type == "Y":
                    death_zone = "边界"
                else:
                    death_zone = cell.cell_type
            else:
                death_zone = "边界"
        
        # 计算方位角（从起始点到agent结束位置）
        bearing = calculate_bearing(start_lat, start_lon, ag.lat, ag.lon)
        
        agent_detail = {
            "Agent编号": idx,
            "存活状态": alive_status,
            "死亡原因": death_reason,
            "死亡区域": death_zone,
            "步进总耗时（秒）": round(ag.total_alive_seconds, 4),
            "直线迁移距离（米）": round(straight_distance, 4),
            "实际路径距离（米）": round(path_distance, 4),
            "方位角（度）": round(bearing, 4)
        }
        agent_data.append(agent_detail)

        if len(ag.path) > 1 and ag.total_alive_seconds >= 0 and straight_distance >= 0:
            total_time += ag.total_alive_seconds
            total_distance += straight_distance
            valid_agents += 1

    avg_time = round(total_time / valid_agents, 4) if valid_agents > 0 else 0.0
    avg_distance = round(total_distance / valid_agents, 4) if valid_agents > 0 else 0.0

    with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
        df_detail = pd.DataFrame(agent_data)
        df_detail.to_excel(writer, sheet_name="Agent详细数据", index=False)

        # 构建输入参数信息
        input_params = {
            "统计项": [
                "=== 模拟输入参数 ===",
                "投射Agent数量",
                "最大模拟步数",
                "实际模拟步数",
                "Agent自速度（米/秒）",
                "投射纬度（度）",
                "投射经度（度）",
                "方向选择模式",
                "洋流影响模式",
                "启用寿命限制",
                "物种寿命（年）",
                "纯满状态生存时间（天）",
                "启用B区域补给",
                "B区域补给百分比（%）",
                "启用全球模拟",
                "方向种子（Direction Seed）",
                "Levy种子（Levy Seed）",
                "LEVY_EXP数值",
                "步进时间缩放因子",
                "=== 模拟统计结果 ===",
                "有效Agent总数",
                "所有Agent总耗时（秒）",
                "所有Agent总迁移距离（米）",
                "平均步进耗时（秒/Agent）",
                "平均迁移距离（米/Agent）",
            ],
            "数值": [
                "",
                n_agents if n_agents is not None else "未设置",
                max_steps if max_steps is not None else "未设置",
                actual_steps if actual_steps is not None else "未设置",
                self_speed if self_speed is not None else "未设置",
                start_lat if start_lat is not None else "未设置",
                start_lon if start_lon is not None else "未设置",
                direction_mode if direction_mode is not None else "未设置",
                current_influence_mode if current_influence_mode is not None else "未设置",
                "是" if enable_lifespan_limit else "否",
                lifespan_years if lifespan_years is not None else "未设置",
                pure_full_state_survival_days if pure_full_state_survival_days is not None else "未设置",
                "是" if enable_b_supply else "否",
                b_supply_percent if b_supply_percent is not None else "未设置",
                "是" if enable_global_simulation else "否",
                direction_seed,
                levy_seed,
                levy_exp if levy_exp is not None else LEVY_EXP_PRIMARY,
                step_time_multiplier if step_time_multiplier is not None else 1,
                "",
                valid_agents,
                round(total_time, 4),
                round(total_distance, 4),
                avg_time,
                avg_distance,
            ]
        }
        df_summary = pd.DataFrame(input_params)
        df_summary.to_excel(writer, sheet_name="统计汇总", index=False)

    # 只有在交互式模式下显示消息框
    if parent_window:
        # 创建自动关闭的消息框
        def auto_close_messagebox():
            # 查找并关闭消息框窗口
            for widget in parent_window.winfo_children():
                if widget.winfo_class() == 'Toplevel':
                    widget.destroy()
                    break
        
        # 显示消息框
        msg_box = messagebox.showinfo(
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
            f"2. 统计汇总（平均值+种子信息）\n\n"
            f"窗口将在3秒后自动关闭...",
            parent=parent_window
        )
        
        # 3秒后自动关闭
        parent_window.after(3000, auto_close_messagebox)


def show_interactive_window(fig, agents, actual_steps: int, max_steps: int,
                            direction_seed: int = None, levy_seed: int = None,
                            levy_exp: float = None, start_lat=None, start_lon=None, 
                            self_speed=None, direction_mode=None, current_influence_mode=None,
                            enable_lifespan_limit=None, lifespan_years=None, 
                            pure_full_state_survival_days=None, enable_b_supply=None, 
                            b_supply_percent=None, enable_global_simulation=None,
                            grid=None, lats_inc=None, lons_inc=None,
                            step_time_multiplier=None, maximize_window: bool = False,
                            record_video: bool = False):
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

    if maximize_window:
        root.state('zoomed')

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
        command=lambda: export_agent_data(agents, root, direction_seed, levy_seed, levy_exp,
                                         start_lat=start_lat, start_lon=start_lon, 
                                         self_speed=self_speed, direction_mode=direction_mode,
                                         current_influence_mode=current_influence_mode,
                                         enable_lifespan_limit=enable_lifespan_limit,
                                         lifespan_years=lifespan_years,
                                         pure_full_state_survival_days=pure_full_state_survival_days,
                                         enable_b_supply=enable_b_supply,
                                         b_supply_percent=b_supply_percent,
                                         enable_global_simulation=enable_global_simulation,
                                         n_agents=len(agents),
                                         max_steps=max_steps,
                                         actual_steps=actual_steps,
                                         grid=grid,
                                         lats_inc=lats_inc,
                                         lons_inc=lons_inc,
                                         step_time_multiplier=step_time_multiplier),
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