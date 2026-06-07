from __future__ import annotations
import math
import random
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from tqdm import tqdm
import gc

# 视频录制相关导入
try:
    import cv2
    VIDEO_AVAILABLE = True
except ImportError:
    VIDEO_AVAILABLE = False

# 导入全局常量
from simulation_constants import *  # 导入所有常量

# 导入独立工具脚本（只导入基本函数，不导入全球模拟函数）
from simulation_utils import (
    # 配置读写相关
    CONFIG_PATH, DEFAULT_CONFIG, load_config, save_config, load_max_migration_seconds,
    # 辅助判断函数
    is_angle_disabled, temperature_to_score,
    # 工具类函数
    bresenham_line, get_grid_index, locate_cell, haversine_distance, default_excel_path,
    # 地图与单元格处理
    GridCell, parse_cell, load_map,
    # 导出与交互模块
    export_png, export_agent_data, show_interactive_window
    # 注意：不要在这里导入全球模拟函数，它们现在在 global_simulation_utils.py 中
)

# 导入全球模拟工具（直接从 global_simulation_utils 导入）
try:
    from global_simulation_utils import (
        normalize_coordinates,  # 现在从 global_simulation_utils 导入
        adjust_direction_for_pole_crossing,
        get_wrap_around_offset,
        GlobalPathManager,
        plot_global_paths,
        update_agent_for_global_simulation,
        check_global_boundary
    )

    GLOBAL_SIM_AVAILABLE = True
except ImportError as e:
    GLOBAL_SIM_AVAILABLE = False
    print(f"警告：全球模拟功能不可用: {e}")


    # 定义空函数作为后备
    def normalize_coordinates(lon, lat):
        return lon, lat


    def adjust_direction_for_pole_crossing(start_lat, end_lat, current_alpha):
        return current_alpha


    def get_wrap_around_offset(lon1, lon2):
        return 0


    class GlobalPathManager:
        def __init__(self, agent_id):
            pass

        def add_point(self, lon, lat):
            pass

        def get_paths_for_plotting(self):
            return []


    def plot_global_paths(ax, agents, color_map=None):
        pass


    def update_agent_for_global_simulation(agent, new_lat, new_lon, alpha):
        return new_lat, new_lon, alpha


    def check_global_boundary(lat, lon, grid, lats_inc, lons_inc, nrows):
        return True

# ---- 全局变量初始化（从配置加载）----
config = load_config()
MAX_MIGRATION_SECONDS = load_max_migration_seconds(config["pure_full_state_survival_days"])
ENABLE_LIFESPAN_TERMINAL = config["enable_lifespan_terminal"]


# 注意：direction_mode 和 current_influence_mode 现在是从配置中读取的
# 它们会在 run_simulation_fast 函数中被设置为局部变量


def calculate_step_duration(levy_rng: np.random.RandomState, levy_exp: float, self_speed: float,
                            step_time_multiplier: int, max_migration_seconds: float, time_since_G: float) -> float:
    """
    计算单次步进的持续时间（秒）
    
    参数:
        levy_rng: Levy步长随机数生成器
        levy_exp: Levy分布指数
        self_speed: 生物自身速度
        step_time_multiplier: 步进时间缩放因子
        max_migration_seconds: 最大无补给存活时间
        time_since_G: 距离上次G区域补给的时间
    
    返回:
        float: 本次步进的持续时间（秒）
    """
    LEVY_TIME_SCALE = LEVY_SCALE / self_speed
    t = LEVY_TIME_SCALE * (levy_rng.pareto(levy_exp) + 1.0)
    t *= step_time_multiplier
    
    remaining_time = max(0.0, max_migration_seconds - time_since_G)
    t = min(t, remaining_time)
    
    return t


def choose_alpha(row: int, col: int, grid_map, temp_map, ignore_disabled=False,
                 dir_rng: random.Random = None, disabled_directions=None, direction_mode="weighted") -> float:
    """
    方向选择逻辑：彻底拆分无温度模式与加权模式，无温度模式完全脱离温度依赖
    - 'random'（无温度模式）：0-360°完全随机，仅遵守方向禁用限制
    - 'weighted'（加权模式）：保留原有50%随机+50%温度加权逻辑
    新增参数：
        dir_rng: 独立的随机生成器（控制方向种子），默认None时使用全局random库（兼容原有调用）
        disabled_directions: 禁用方向字典，从配置或全局常量获取
        direction_mode: 方向模式（"random" 或 "weighted"）
    """
    # 如果未传入 disabled_directions，使用默认值
    if disabled_directions is None:
        from simulation_constants import disabled_directions as default_disabled
        disabled_directions = default_disabled

    # 关键：如果未传入dir_rng，使用全局random（兼容原有逻辑，避免报错）
    if dir_rng is None:
        dir_rng = random

    # ==================== 无温度模式（Random Mode）====================
    if direction_mode == "random":
        max_attempts = 200
        for _ in range(max_attempts):
            # 替换：random.uniform → dir_rng.uniform（使用独立生成器）
            angle = dir_rng.uniform(0, 360)
            # 关键修改：传入 disabled_directions 参数
            if ignore_disabled or not is_angle_disabled(angle, disabled_directions):
                return angle
        return 0.0

    # ==================== 加权模式（Weighted Mode）====================
    nrows, ncols = len(grid_map), len(grid_map[0])
    if not (0 <= row < nrows and 0 <= col < ncols):
        max_attempts = 100
        for _ in range(max_attempts):
            # 替换：random.uniform → dir_rng.uniform
            angle = dir_rng.uniform(0, 360)
            # 关键修改：传入 disabled_directions 参数
            if ignore_disabled or not is_angle_disabled(angle, disabled_directions):
                return angle
        return 0.0

    # 加权模式：50%概率随机（过滤禁用方向）
    # 替换：random.random → dir_rng.random（控制随机概率的种子）
    if dir_rng.random() < 0.5:
        max_attempts = 100
        for _ in range(max_attempts):
            # 替换：random.uniform → dir_rng.uniform
            angle = dir_rng.uniform(0, 360)
            # 关键修改：传入 disabled_directions 参数
            if ignore_disabled or not is_angle_disabled(angle, disabled_directions):
                return angle
        return 0.0

    # 加权模式：50%概率温度加权（过滤禁用方向）
    directions = [
        (-1, 0, 0),
        (-1, 1, 45),
        (0, 1, 90),
        (1, 1, 135),
        (1, 0, 180),
        (1, -1, 225),
        (0, -1, 270),
        (-1, -1, 315),
    ]

    ray_data = []
    for dr, dc, angle in directions:
        nr, nc = row + dr, col + dc
        if 0 <= nr < nrows and 0 <= nc < ncols:
            cell_type = grid_map[nr][nc]
            if cell_type in ("B", "G"):
                try:
                    temp_val = float(temp_map[nr, nc])
                    ray_data.append((angle, temp_val))
                except Exception:
                    ray_data.append((angle, None))
            else:
                ray_data.append((angle, None))
        else:
            ray_data.append((angle, None))

    full_rays = []
    for i in range(len(ray_data)):
        angle1, t1 = ray_data[i]
        full_rays.append((angle1, t1))
        angle2, t2 = ray_data[(i + 1) % len(ray_data)]
        if (t1 is not None) and (t2 is not None):
            diff = (angle2 - angle1 + 360) % 360
            if diff > 180:
                diff -= 360
            mid_angle = (angle1 + diff / 2) % 360
            mid_temp = (t1 + t2) / 2.0
            full_rays.append((mid_angle, mid_temp))

    # 过滤：仅保留非禁用方向且有温度数据的方向
    scored_rays = []
    for angle, temp in full_rays:
        # 关键修改：传入 disabled_directions 参数
        if temp is not None and (ignore_disabled or not is_angle_disabled(angle, disabled_directions)):
            score = temperature_to_score(temp)
            if score > 0.0:
                scored_rays.append((angle % 360, score))

    # 无合法温度加权方向时，退化为随机（过滤禁用）
    if not scored_rays:
        max_attempts = 100
        for _ in range(max_attempts):
            # 替换：random.uniform → dir_rng.uniform
            angle = dir_rng.uniform(0, 360)
            # 关键修改：传入 disabled_directions 参数
            if ignore_disabled or not is_angle_disabled(angle, disabled_directions):
                return angle
        return 0.0

    angles, scores = zip(*scored_rays)
    scores = np.array(scores, dtype=float)
    probs = scores / scores.sum()
    # 替换：random.choices → dir_rng.choices（温度加权方向的随机选择）
    chosen_angle = dir_rng.choices(angles, weights=probs, k=1)[0]
    return float(chosen_angle % 360)

    # 在 Agent 类的 __init__ 方法中添加：
class Agent:
    """生物个体类"""

    def __init__(self, lat: float, lon: float, dir_rng: random.Random, levy_rng: np.random.RandomState,
                 levy_exp: float, self_speed: float, enable_global_simulation: bool = False,
                 max_migration_seconds: float = 0.0, agent_id: int = 0, step_time_multiplier: int = 1):
        self.id = agent_id  # 存储Agent编号
        self.lat = lat
        self.lon = lon
        self.alive = True
        self.was_alive = True  # 用于跟踪Agent在上一次迭代中的存活状态
        self.time_since_G = 0.0
        self.path = [(lat, lon)]  # 保留普通路径记录
        self.total_alive_seconds = 0.0
        self.death_type = "alive"  # 初始化为"alive"，死亡时改为具体类型
        self.dir_rng = dir_rng
        self.levy_rng = levy_rng
        self.levy_exp = levy_exp
        self.self_speed = self_speed
        self.enable_global_simulation = enable_global_simulation
        self.max_migration_seconds = max_migration_seconds
        self.step_time_multiplier = step_time_multiplier  # 步进时间缩放因子

        # 如果是全球模拟模式，初始化路径管理器
        if self.enable_global_simulation:
            self.global_path_manager = GlobalPathManager(id(self))
            # 添加初始点
            self.global_path_manager.add_point(lon, lat)

    def step(self, grid, lats_inc, lons_inc, temp_map, grid_cell_types,
             current_influence_mode: str, ENABLE_LIFESPAN_LIMIT: bool = False,
             LIFESPAN_YEARS: float = 0.0, direction_mode: str = "weighted"):
        """
        执行单步移动

        参数:
            current_influence_mode: 洋流影响模式
            ENABLE_LIFESPAN_LIMIT: 是否启用寿命限制
            LIFESPAN_YEARS: 寿命年限
            direction_mode: 方向模式（"random" 或 "weighted"）
            
        返回:
            float: 本次移动的步进时长（秒），如果Agent已死亡或未移动则返回0.0
        """
        if not self.alive:
            return 0.0

        # 调试：记录起始位置
        # print(f"Agent step start: lat={self.lat}, lon={self.lon}, global_mode={self.enable_global_simulation}")

        if self.enable_global_simulation:
            # 确保当前位置已标准化
            self.lon, self.lat = normalize_coordinates(self.lon, self.lat)
            # 初始化全局路径管理器
            if not hasattr(self, 'global_path_manager'):
                self.global_path_manager = GlobalPathManager(id(self))
                # 添加起点到全局路径管理器
                self.global_path_manager.add_point(self.lon, self.lat)
            # print(f"After normalization: lat={self.lat}, lon={self.lon}")
        else:
            # 非全球模拟模式下，确保不初始化全局路径管理器
            # 修复：移除可能错误初始化的全局路径管理器
            if hasattr(self, 'global_path_manager'):
                delattr(self, 'global_path_manager')

        # ------------ 使用实例变量self.levy_exp和self.self_speed ------------
        # 调用独立函数计算步进持续时间
        t = calculate_step_duration(
            levy_rng=self.levy_rng,
            levy_exp=self.levy_exp,
            self_speed=self.self_speed,
            step_time_multiplier=self.step_time_multiplier,
            max_migration_seconds=self.max_migration_seconds,
            time_since_G=self.time_since_G
        )
        # -------------------------------------------------------------------

        # 累加总存活时间
        self.total_alive_seconds += t

        # 获取起点网格索引，传递 enable_global_simulation 参数
        nrows, ncols = grid.shape
        start_idx = get_grid_index(self.lat, self.lon, lats_inc, lons_inc, nrows, self.enable_global_simulation)
        if start_idx is None:
            self.alive = False
            self.death_type = "out_of_bounds"
            return
        start_i, start_j = start_idx

        # 选择初始方向alpha
        current_cell = grid[start_i, start_j]
        ignore_disabled = current_cell.cell_type == "Y"
        try:
            # 传入独立方向生成器，控制方向种子
            # 修复：使用传入的direction_mode参数而不是全局变量
            from simulation_constants import disabled_directions
            alpha = choose_alpha(start_i, start_j, grid_cell_types, temp_map,
                                 ignore_disabled=ignore_disabled,
                                 dir_rng=self.dir_rng,
                                 disabled_directions=disabled_directions,
                                 direction_mode=direction_mode)  # 修复：传递direction_mode参数
        except Exception:
            # 异常时用独立生成器，而非全局random
            alpha = self.dir_rng.uniform(0, 360)

        # 计算初步终点（基于起点洋流）
        a = math.radians(alpha)
        v_self_e = self.self_speed * math.sin(a)  # 使用实例的速度
        v_self_n = self.self_speed * math.cos(a)  # 使用实例的速度

        # 在调用 locate_cell 时传递 enable_global_simulation 参数
        cell_start = locate_cell(self.lat, self.lon, grid, lats_inc, lons_inc, self.enable_global_simulation)
        if cell_start is None and not self.enable_global_simulation:  # 全球模拟不禁用边界死亡
            self.alive = False
            self.death_type = "out_of_bounds"
            return

        # 根据洋流影响模式决定是否应用洋流影响
        if current_influence_mode == "with_current":
            v_cur_e, v_cur_n = cell_start.current_vector()
        else:
            v_cur_e, v_cur_n = 0.0, 0.0
        v_e = v_self_e + v_cur_e
        v_n = v_self_n + v_cur_n
        v_mag = math.hypot(v_e, v_n)
        if v_mag == 0.0:
            return

        d = v_mag * t  # 总移动距离
        dn = d * (v_n / v_mag)
        de = d * (v_e / v_mag)
        cosphi = max(1e-9, math.cos(math.radians(self.lat)))
        dlat = dn / M_PER_DEG_LAT
        dlon = de / (M_PER_DEG_LAT * cosphi)
        end_lat = self.lat + dlat
        end_lon = self.lon + dlon

        # 获取终点网格索引
        end_idx = get_grid_index(end_lat, end_lon, lats_inc, lons_inc, nrows, self.enable_global_simulation)
        if end_idx is None and not self.enable_global_simulation:
            self.alive = False
            self.death_type = "out_of_bounds"
            return
        elif end_idx is None and self.enable_global_simulation:
            # 全球模拟模式下，使用边界上的索引
            end_i = max(0, min(nrows - 1, int(np.floor(nrows - (np.searchsorted(lats_inc, end_lat, 'right') - 1)))))
            end_j = max(0, min(ncols - 1, int(np.searchsorted(lons_inc, end_lon, 'right') - 1)))
        else:
            end_i, end_j = end_idx

        # 使用Bresenham算法获取网格路径
        grid_path = bresenham_line(start_i, start_j, end_i, end_j)

        # 如果起点终点在同一网格，简单移动
        if len(grid_path) == 1:
            new_lat, new_lon = end_lat, end_lon

            # 检查路径是否穿越陆地
            if not self._crosses_land(self.lat, self.lon, new_lat, new_lon, grid, lats_inc, lons_inc):
                # 如果是全球模拟，处理坐标标准化和方向调整
                if self.enable_global_simulation:
                    from global_simulation_utils import update_agent_for_global_simulation
                    norm_lat, norm_lon, alpha = update_agent_for_global_simulation(
                        self, new_lat, new_lon, alpha
                    )
                    self.lat, self.lon = norm_lat, norm_lon
                else:
                    self.lat, self.lon = new_lat, new_lon

                # 记录路径
                self._record_path_point(self.lat, self.lon)
        else:
            # 自适应分段移动
            current_lat, current_lon = self.lat, self.lon
            elapsed_time = 0.0

            for seg_idx in range(len(grid_path) - 1):
                if elapsed_time >= t:
                    break

                i, j = grid_path[seg_idx]
                if not (0 <= i < nrows and 0 <= j < ncols):
                    break

                # 判断是否启用洋流影响
                if current_influence_mode == "with_current":
                    cell_current = grid[i, j]
                    v_cur_e_seg, v_cur_n_seg = cell_current.current_vector()
                else:
                    v_cur_e_seg, v_cur_n_seg = 0.0, 0.0

                # 重新计算合成速度
                v_e_seg = v_self_e + v_cur_e_seg
                v_n_seg = v_self_n + v_cur_n_seg
                v_mag_seg = math.hypot(v_e_seg, v_n_seg)
                if v_mag_seg == 0.0:
                    continue

                # 计算本段可用时间
                segment_time = min(t - elapsed_time, t / max(1, len(grid_path)))

                # 计算本段位移
                d_seg = v_mag_seg * segment_time
                dn_seg = d_seg * (v_n_seg / v_mag_seg)
                de_seg = d_seg * (v_e_seg / v_mag_seg)
                cosphi_seg = max(1e-9, math.cos(math.radians(current_lat)))
                dlat_seg = dn_seg / M_PER_DEG_LAT
                dlon_seg = de_seg / (M_PER_DEG_LAT * cosphi_seg)

                new_lat_seg = current_lat + dlat_seg
                new_lon_seg = current_lon + dlon_seg

                # 检查路径是否穿越陆地
                if self._crosses_land(current_lat, current_lon, new_lat_seg, new_lon_seg,
                                      grid, lats_inc, lons_inc):
                    break

                # 如果是全球模拟，处理坐标标准化
                if self.enable_global_simulation:
                    from global_simulation_utils import update_agent_for_global_simulation
                    norm_lat, norm_lon, alpha = update_agent_for_global_simulation(
                        self, new_lat_seg, new_lon_seg, alpha
                    )
                    current_lat, current_lon = norm_lat, norm_lon
                else:
                    current_lat, current_lon = new_lat_seg, new_lon_seg

                elapsed_time += segment_time

                # 记录路径点
                self._record_path_point(current_lat, current_lon)

            self.lat, self.lon = current_lat, current_lon

        # 从配置中获取B区域补给设置
        from simulation_constants import DEFAULT_CONFIG
        config = load_config()
        enable_b_supply = config.get("enable_b_supply", DEFAULT_CONFIG["enable_b_supply"])
        b_supply_percent = config.get("b_supply_percent", DEFAULT_CONFIG["b_supply_percent"])
        
        # 第一步：更新time_since_G（使用放大后的t，确保与step_time_multiplier同步）
        target_cell = locate_cell(self.lat, self.lon, grid, lats_inc, lons_inc, self.enable_global_simulation)
        if target_cell is None and not self.enable_global_simulation:  # 全球模拟不禁用边界死亡
            self.alive = False
            self.death_type = "out_of_bounds"
            return t
        
        # 更新time_since_G（使用已放大的t，确保流逝速度与step_time_multiplier同步）
        if target_cell.cell_type == "G":
            self.time_since_G = 0.0
        elif target_cell.cell_type == "B" and enable_b_supply:
            b_supply_factor = b_supply_percent / 100.0
            reduction_amount = self.max_migration_seconds * b_supply_factor
            self.time_since_G += t  # 先增加时间（使用放大后的t）
            self.time_since_G = max(0.0, self.time_since_G - reduction_amount)
        else:
            self.time_since_G += t  # 普通区域和未启用补给的B区域（使用放大后的t）
        
        # 第二步：检查死亡条件（在time_since_G更新之后）
        # 补给超时死亡检查（time_since_G已使用放大后的t更新）
        if self.time_since_G >= self.max_migration_seconds:
            self.alive = False
            self.death_type = "supply"
            print(f"Agent[{self.id}] 补给超时死亡: time_since_G={self.time_since_G:.1f}, max={self.max_migration_seconds:.1f}")
            return t  # 直接返回，不再进行后续处理
        
        # 寿命到期死亡（仅启用寿命限制时）
        if ENABLE_LIFESPAN_LIMIT and self.alive:
            max_life_seconds = LIFESPAN_YEARS * 365 * 24 * 3600
            if self.total_alive_seconds > max_life_seconds:
                self.alive = False
                self.death_type = "lifespan"
                print(f"Agent[{self.id}] 寿命到期死亡: total_alive_seconds={self.total_alive_seconds:.1f}, max={max_life_seconds:.1f}")
                return t  # 直接返回，不再进行后续处理
        
        # 返回本次移动的步进时长
        return t

    def _record_path_point(self, lat: float, lon: float):
        """
        记录路径点（辅助方法）

        参数:
            lat: 纬度
            lon: 经度
        """
        # 添加到普通路径列表
        self.path.append((lat, lon))

        # 如果是全球模拟，添加到全局路径管理器
        if self.enable_global_simulation:
            if not hasattr(self, 'global_path_manager'):
                self.global_path_manager = GlobalPathManager(id(self))
                # 添加历史路径点
                for path_lat, path_lon in self.path:
                    self.global_path_manager.add_point(path_lon, path_lat)
            else:
                self.global_path_manager.add_point(lon, lat)

    def _crosses_land(self, lat1, lon1, lat2, lon2, grid, lats_inc, lons_inc, n_samples=20):
        """检查路径是否穿越陆地（优化版）"""
        # 提前检查起点是否在陆地
        start_cell = locate_cell(lat1, lon1, grid, lats_inc, lons_inc, self.enable_global_simulation)
        if start_cell is not None and start_cell.cell_type == "Y":
            return True
        
        # 使用快速距离近似计算（避免haversine的复杂三角函数）
        # 对于采样点计算，不需要高精度距离
        delta_lat = abs(lat2 - lat1)
        delta_lon = abs(lon2 - lon1)
        
        # 简化的距离估算：使用经纬度差的平方和平方根
        # 乘以平均每度距离（约111公里）得到近似距离（米）
        # 为了保守估计采样点数，使用略小的系数（100公里/度）
        distance_estimate_m = math.hypot(delta_lat, delta_lon) * 100 * 1000
        
        # 采样策略：每200公里一个采样点，且包含终点
        SAMPLE_INTERVAL_M = 200 * 1000  # 200公里 = 200000米
        
        # 计算采样点数：距离 / 200公里，向上取整
        if distance_estimate_m <= SAMPLE_INTERVAL_M:
            # 距离小于等于200公里，只检测终点
            num_samples = 1
        else:
            # 距离大于200公里，按每200公里一个采样点计算
            num_samples = int(math.ceil(distance_estimate_m / SAMPLE_INTERVAL_M))
        
        # 缓存全局模拟设置，避免重复属性访问
        global_sim = self.enable_global_simulation
        
        # 计算步长（包含终点）
        dlat = (lat2 - lat1) / num_samples
        dlon = (lon2 - lon1) / num_samples
        
        # 采样检测（包含终点）
        for k in range(1, num_samples + 1):
            lat = lat1 + dlat * k
            lon = lon1 + dlon * k

            # 如果是全球模拟，先标准化坐标
            if global_sim:
                lon, lat = normalize_coordinates(lon, lat)

            cell = locate_cell(lat, lon, grid, lats_inc, lons_inc, global_sim)
            if cell is not None and cell.cell_type == "Y":
                return True
        
        return False


# ---- 核心模拟函数 -----------------------------------------------------
def run_simulation_fast(
        excel_path,
        n_agents,
        max_steps,
        direction_seed=None,
        levy_seed=None,
        temp_path=None,
        levy_exp=LEVY_EXP_PRIMARY,
        enable_lifespan_terminal=False,
        max_life_seconds=0,
        direction_mode="weighted",
        show_interactive=True,
        enable_global_simulation=True,  # 新增：启用全球模拟
        export_prefix="simulation",
        enable_b_supply=False,
        b_supply_percent=50.0,
        start_lat=None,
        start_lon=None,
        self_speed=None,
        pure_survival_days=None,
        current_influence_mode=None,
        enable_lifespan_limit=None,
        lifespan_years=None,
        verbose_params=True,  # 新增：控制参数信息打印
        step_time_multiplier=1,  # 新增：步进时间缩放因子
        maximize_window=False,  # 新增：模拟结束后是否最大化窗口
        auto_save_visualization=False,  # 新增：是否在模拟过程中自动保存可视化
        record_video=False  # 新增：是否录制模拟视频
):
    """修复：正确使用配置参数而不是全局变量"""
    # 加载配置获取最新的用户输入
    config = load_config()

    # 修复：使用传入的参数值而不是配置中的值
    # 确保传入的参数值优先于配置文件中的默认值
    start_lat_local = start_lat if start_lat is not None else config["start_lat"]
    start_lon_local = start_lon if start_lon is not None else config["start_lon"]
    SELF_SPEED_local = self_speed if self_speed is not None else config["self_speed"]
    current_influence_mode_local = current_influence_mode if current_influence_mode is not None else config["current_influence_mode"]
    ENABLE_LIFESPAN_LIMIT_local = enable_lifespan_limit if enable_lifespan_limit is not None else config["enable_lifespan_limit"]
    LIFESPAN_YEARS_local = lifespan_years if lifespan_years is not None else config["lifespan_years"]
    pure_full_state_survival_days = pure_survival_days if pure_survival_days is not None else config["pure_full_state_survival_days"]

    # 计算基于配置的迁移时间
    MAX_MIGRATION_SECONDS = load_max_migration_seconds(pure_full_state_survival_days)

    # 如果启用了寿命限制，使用配置中的寿命值
    if ENABLE_LIFESPAN_LIMIT_local:
        max_life_seconds = LIFESPAN_YEARS_local * 365 * 24 * 3600

    # 控制参数信息打印：verbose_params=True时打印完整信息，False时只打印关键差异
    if verbose_params:
        print(f"使用的起点坐标: lat={start_lat_local}, lon={start_lon_local}")
        print(f"使用的自速度: {SELF_SPEED_local}")
        print(f"使用的洋流模式: {current_influence_mode_local}")
        print(f"使用的方向模式: {direction_mode}")
        print(f"使用的寿命限制: {ENABLE_LIFESPAN_LIMIT_local}, 寿命年数: {LIFESPAN_YEARS_local}")

        # --------- 初始化种子（用于为每个Agent创建独立RNG） ----------
        # 记录基础种子用于复现
        if direction_seed is None:
            direction_seed = random.randint(0, 1000000)
            print(f"方向种子留空，自动生成基础种子：{direction_seed}（记录可复现）")
        else:
            print(f"已设置基础方向种子：{direction_seed}（方向选择可复现）")

        if levy_seed is None:
            levy_seed = np.random.randint(0, 1000000)
            print(f"Levy种子留空，自动生成基础种子：{levy_seed}（记录可复现）")
        else:
            print(f"已设置基础Levy步长种子：{levy_seed}（步长t可复现）")
    else:
        # 非详细模式：只打印关键差异信息
        print(f"导出前缀: {export_prefix}")
        if direction_seed is None:
            direction_seed = random.randint(0, 1000000)
        if levy_seed is None:
            levy_seed = np.random.randint(0, 1000000)

    print(f"当前模拟LEVY_EXP：{levy_exp}")

    # 处理 temp_path：空字符串或不存在文件 => None
    if temp_path == "" or (temp_path is not None and not Path(temp_path).exists()):
        temp_path = None

    # 加权模式：确保 temp_path 非空且文件存在
    if direction_mode == "weighted":
        if temp_path is None or not Path(temp_path).exists():
            raise FileNotFoundError(
                "Temperature file path is required (weighted mode).\nPlease select a valid Excel file."
            )

    # 1. 加载地图（调用工具脚本函数）
    grid = load_map(excel_path)
    nrows, ncols = grid.shape

    # 2. 经纬度分割
    lats_inc = np.linspace(MIN_LAT, MAX_LAT, nrows + 1)
    lons_inc = np.linspace(MIN_LON, MAX_LON, ncols + 1)

    # 3. 处理温度数据（仅 weighted 模式需要）
    temp_map = None
    if direction_mode == "weighted":
        temp_df = pd.read_excel(temp_path, header=None)
        temp_arr = temp_df.to_numpy(dtype=float)
        if temp_arr.shape != (nrows, ncols):
            raise ValueError("Temperature table size does not match map grid.")
        temp_map = temp_arr

    # 4. grid_cell_types 用于 choose_alpha
    grid_cell_types = [[grid[i, j].cell_type for j in range(ncols)] for i in range(nrows)]

    # 5. 创建 agents（为每个Agent创建独立的随机数生成器）
    agents = []
    for i in range(n_agents):
        # 为每个Agent创建独立的方向随机数生成器
        agent_dir_rng = random.Random()
        agent_dir_rng.seed(direction_seed + i)  # 使用基础种子+Agent索引确保独立性
        
        # 为每个Agent创建独立的Levy步长随机数生成器
        agent_levy_rng = np.random.RandomState()
        agent_levy_rng.seed(levy_seed + i)  # 使用基础种子+Agent索引确保独立性
        
        agents.append(Agent(
            start_lat_local, start_lon_local, 
            agent_dir_rng, agent_levy_rng,  # 传入独立的RNG实例
            levy_exp, SELF_SPEED_local, 
            enable_global_simulation, MAX_MIGRATION_SECONDS, i,
            step_time_multiplier  # 传递步进时间缩放因子
        ))
    print(f"初始投射地点：lat={start_lat_local}, lon={start_lon_local}")

    # 调试信息
    start_idx = get_grid_index(start_lat_local, start_lon_local, lats_inc, lons_inc, nrows)
    if start_idx:
        print(f"起点网格索引：{start_idx}")
    else:
        print(f"警告：起点坐标超出地图范围")

    # 6. 绘制基础地图
    grid_img = np.zeros((nrows, ncols))
    for i in range(nrows):
        for j in range(ncols):
            t = grid[i, j].cell_type
            grid_img[i, j] = 0 if t == "B" else (1 if t == "G" else 2)
    cmap = ListedColormap([[0.2, 0.4, 0.8], [0.6, 0.9, 0.9], [0.25, 0.25, 0.25]])

    # 性能阈值（控制实时渲染）
    total_data = max_steps * n_agents
    threshold = 100000 * 10  # 大于该计算量后台运算
    use_realtime_refresh = total_data < threshold

    # 进度条
    pbar = None  
    try:
        if enable_lifespan_terminal:
            pbar = tqdm(total=n_agents, desc="Simulation Progress (Agents Reached Lifespan)", unit="agent")
            completed_agents = 0
        else:
            # 改进的传统步数模式进度条：动态调整剩余步数
            pbar = tqdm(total=max_steps, desc="Simulation Progress", unit="step")
            # 记录初始活跃agent数量
            initial_alive_count = n_agents
            # 记录死亡速度统计
            death_stats = {
                'total_deaths': 0,
                'steps_since_last_death': 0,
                'death_rate': 0.0,
                'estimated_remaining_steps': max_steps
            }
    except Exception:
        pbar = None

    # 图形准备 - 仅在show_interactive=True时创建图形
    fig = None
    ax = None
    
    # 仅在需要显示交互窗口时才创建图形
    if show_interactive:
        try:
            plt.ion()  # 开启交互模式
            fig, ax = plt.subplots(figsize=(12, 7), num="Marine Organism Levy Flight Simulation")
            ax.imshow(grid_img, cmap=cmap, origin="upper",
                      extent=[MIN_LON, MAX_LON, MIN_LAT, MAX_LAT],
                      interpolation="nearest", aspect="auto")
            fig.show()  # 立即显示图形窗口
        except Exception as e:
            # 若图形系统不可用，继续模拟但不绘图
            print(f"[Warning] matplotlib 绘图失败，切换为无界面模式: {e}")
            fig = None
            ax = None

    path_lines = []  # 存储路径线
    agent_points = []  # 存储agent当前位置点
    agent_colors = []  # 存储每个agent的唯一颜色
    # 初始化图形界面元素（只要show_interactive=True就初始化）
    if fig is not None and show_interactive:
        try:
            # 为每个agent生成唯一颜色
            agent_colors = plt.cm.Set1(np.linspace(0, 1, len(agents)))
            
            # 为每个agent创建一个用于显示当前位置的点
            agent_points = [ax.plot([], [], marker="o", markersize=2, alpha=0.7, color=color)[0] for _, color in zip(agents, agent_colors)]
            # 为每个agent创建一组用于显示路径段的线条
            path_lines = [[] for _ in agents]
        except Exception as e:
            print(f"[Warning] 初始化图形元素失败: {e}")
            agent_points = []
            path_lines = []
            agent_colors = []

    # 视频录制初始化
    video_writer = None
    if record_video and VIDEO_AVAILABLE and fig is not None:
        try:
            # 获取画布尺寸
            canvas_width, canvas_height = fig.get_size_inches() * fig.dpi
            video_size = (int(canvas_width), int(canvas_height))
            
            # 创建视频写入器
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            video_path = f"simulation_video_{timestamp}.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(video_path, fourcc, 10.0, video_size)
            print(f"视频录制已启动，将保存到: {video_path}")
        except Exception as e:
            print(f"视频录制初始化失败: {e}")
            video_writer = None

    # 实时刷新间隔（只要show_interactive=True就启用实时刷新）
    if show_interactive:
        if enable_lifespan_terminal:
            refresh_interval = 100
        else:
            refresh_interval = max(1, int(max_steps * 0.02))
    else:
        refresh_interval = None

    # ---- 主循环（放在 try/finally 以确保资源释放） ----
    actual_steps = 0
    try:
        while True:
            actual_steps += 1

            # 更新每个 agent
            for ag in agents:
                if not ag.alive or (enable_lifespan_terminal and ag.total_alive_seconds >= max_life_seconds):
                    continue
                # 接收step方法返回的步进时长
                step_duration = ag.step(grid, lats_inc, lons_inc, temp_map, grid_cell_types,
                                      current_influence_mode_local, ENABLE_LIFESPAN_LIMIT_local, LIFESPAN_YEARS_local, direction_mode)
                # 可以在这里使用步进时长进行额外处理，比如记录每个agent的移动时间
                # 示例：可以将步进时长存储到agent对象中或进行统计分析
                # ag.recent_step_durations.append(step_duration)

            # 实时刷新（只要show_interactive=True且图形存在就刷新）
            if fig is not None and show_interactive and refresh_interval is not None:
                if actual_steps % refresh_interval == 0:
                    # 实时计算死亡统计
                    alive_count = sum(1 for a in agents if a.alive)
                    lifespan_death_count = sum(1 for a in agents if not a.alive and a.death_type == "lifespan")
                    supply_death_count = sum(1 for a in agents if not a.alive and a.death_type == "supply")
                    bounds_death_count = sum(1 for a in agents if not a.alive and a.death_type == "out_of_bounds")
                    
                    # 调试：显示死亡统计 - 已移除
                    
                    # 实时显示死亡的Agent信息
                    if actual_steps % refresh_interval == 0:
                        # 检查并打印在最近一次迭代中死亡的Agent
                        for i, ag in enumerate(agents):
                            # 检查Agent是否在最近一次迭代中死亡
                            if hasattr(ag, 'was_alive') and ag.was_alive and not ag.alive:
                                # 确定死亡原因的中文描述
                                death_reason = ""
                                if ag.death_type == "supply":
                                    death_reason = "补给不足"
                                elif ag.death_type == "lifespan":
                                    death_reason = "寿命到期"
                                elif ag.death_type == "out_of_bounds":
                                    death_reason = "超出边界"
                                else:
                                    death_reason = ag.death_type
                                
                                # 打印死亡Agent的信息
                                print(f"[运行信息] Agent {i+1} 已死亡，死亡原因: {death_reason}")
                        
                        # 确保输出被刷新
                        import sys
                        sys.stdout.flush()
                    
                    # 更新所有Agent的存活状态记录
                    for ag in agents:
                        ag.was_alive = ag.alive

                    if enable_lifespan_terminal:
                        ax.set_title(f"Step {actual_steps} | Alive: {alive_count} | "
                                     f"Lifespan Deaths: {lifespan_death_count} | Supply Deaths: {supply_death_count} | "
                                     f"Completed Agents: {completed_agents}/{n_agents}")
                    else:
                        ax.set_title(f"Step {actual_steps}/{max_steps} | Alive: {alive_count} | "
                                     f"Lifespan Deaths: {lifespan_death_count} | Supply Deaths: {supply_death_count}")

                    for i, (ag, point_line) in enumerate(zip(agents, agent_points)):
                        # 更新agent的当前位置
                        point_line.set_data([ag.lon], [ag.lat])
                        
                        # 绘制路径段
                        if ag.enable_global_simulation and hasattr(ag, 'global_path_manager') and ag.global_path_manager:
                            paths = ag.global_path_manager.get_paths_for_plotting()
                            
                            # 移除旧的路径段
                            for line in path_lines[i]:
                                line.remove()
                            path_lines[i].clear()
                            
                            # 绘制新的路径段
                            for path_lons, path_lats in paths:
                                if len(path_lons) > 1:
                                    line = ax.plot(path_lons, path_lats, linewidth=0.5, alpha=0.7, color=agent_colors[i])[0]
                                    path_lines[i].append(line)
                        elif len(ag.path) > 1:
                            # 普通模式下，使用原始path数据
                            ys, xs = zip(*ag.path)
                            
                            # 移除旧的路径段
                            for line in path_lines[i]:
                                line.remove()
                            path_lines[i].clear()
                            
                            # 绘制完整路径
                            line = ax.plot(xs, ys, linewidth=0.5, alpha=0.7, color=agent_colors[i])[0]
                            path_lines[i].append(line)
                    # 仅在show_interactive=True时更新图形
                    if show_interactive and fig is not None:
                        try:
                            fig.canvas.draw_idle()
                            plt.pause(0.001)
                            
                            # 录制视频帧
                            if video_writer is not None:
                                fig.canvas.draw()
                                frame = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
                                frame = frame.reshape(fig.canvas.get_width_height()[::-1] + (3,))
                                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                                video_writer.write(frame)
                        except Exception:
                            pass

            # 以累计寿命为终止模式
            if enable_lifespan_terminal:
                new_completed = sum(1 for ag in agents if not ag.alive or ag.total_alive_seconds >= max_life_seconds)
                if new_completed > completed_agents and pbar is not None:
                    pbar.update(new_completed - completed_agents)
                    completed_agents = new_completed
                if completed_agents == n_agents:
                    # 重新计算死亡统计
                    lifespan_death_count = sum(1 for a in agents if not a.alive and a.death_type == "lifespan")
                    supply_death_count = sum(1 for a in agents if not a.alive and a.death_type == "supply")
                    bounds_death_count = sum(1 for a in agents if not a.alive and a.death_type == "out_of_bounds")
                    
                    print(f"\n所有Agent已在第{actual_steps}步完成（死亡或达到最大寿命），开始渲染Levy路线...")
                    print(f"完成统计: 补给死亡={supply_death_count}, 寿命死亡={lifespan_death_count}, 边界死亡={bounds_death_count}")
                    
                    # 先完成当前步的渲染（如果启用了交互模式）
                    if fig is not None and show_interactive:
                        try:
                            # 绘制所有agent的完整路径
                            for i, ag in enumerate(agents):
                                if len(ag.path) > 1:
                                    # 获取路径点
                                    ys, xs = zip(*ag.path)
                                    # 清除之前的路径线（如果有）
                                    if i < len(path_lines) and path_lines[i]:
                                        for line in path_lines[i]:
                                            line.remove()
                                        path_lines[i].clear()
                                    
                                    # 绘制完整路径
                                    line = ax.plot(xs, ys, linewidth=0.5, alpha=0.7, color=agent_colors[i])[0]
                                    path_lines[i].append(line)
                            
                            # 强制刷新画布
                            fig.canvas.draw_idle()
                            plt.pause(0.1)  # 短暂暂停确保渲染完成
                        except Exception as e:
                            print(f"渲染Levy路线时出错: {e}")
                    
                    # 完成渲染后，再终止模拟
                    if pbar is not None:
                        pbar.close()
                    break

            # 传统步数模式
            else:
                if pbar is not None:
                    # 智能进度更新：考虑agent死亡对剩余时间的影响
                    alive_count = sum(1 for a in agents if a.alive)
                    current_deaths = initial_alive_count - alive_count
                    
                    # 更新死亡统计
                    if current_deaths > death_stats['total_deaths']:
                        # 有新的死亡发生
                        new_deaths = current_deaths - death_stats['total_deaths']
                        death_stats['total_deaths'] = current_deaths
                        death_stats['death_rate'] = current_deaths / actual_steps if actual_steps > 0 else 0
                        death_stats['steps_since_last_death'] = 0
                    else:
                        death_stats['steps_since_last_death'] += 1
                    
                    # 动态调整进度条预测
                    if alive_count > 0 and death_stats['death_rate'] > 0:
                        # 基于当前死亡率预测剩余步数
                        estimated_steps_to_completion = min(
                            max_steps - actual_steps,  # 不超过最大步数
                            int(alive_count / death_stats['death_rate']) if death_stats['death_rate'] > 0 else max_steps - actual_steps
                        )
                        death_stats['estimated_remaining_steps'] = estimated_steps_to_completion
                        
                        # 更新进度条描述，显示更准确的预测
                        pbar.set_description(f"Simulation Progress ({alive_count}/{initial_alive_count} alive)")
                    
                    pbar.update(1)
                
                # 检查所有Agent是否都已死亡
                alive_count = sum(1 for a in agents if a.alive)
                if alive_count == 0:
                    # 在死亡终止时重新计算死亡统计，确保数据准确
                    lifespan_death_count = sum(1 for a in agents if not a.alive and a.death_type == "lifespan")
                    supply_death_count = sum(1 for a in agents if not a.alive and a.death_type == "supply")
                    bounds_death_count = sum(1 for a in agents if not a.alive and a.death_type == "out_of_bounds")
                    
                    print(f"\n所有Agent已在第{actual_steps}步死亡，开始渲染Levy路线...")
                    print(f"死亡统计: 补给死亡={supply_death_count}, 寿命死亡={lifespan_death_count}, 边界死亡={bounds_death_count}")
                    
                    # 先完成当前步的渲染（如果启用了交互模式）
                    if fig is not None and show_interactive:
                        try:
                            # 绘制所有agent的完整路径
                            for i, ag in enumerate(agents):
                                if len(ag.path) > 1:
                                    # 获取路径点
                                    ys, xs = zip(*ag.path)
                                    # 清除之前的路径线（如果有）
                                    if i < len(path_lines) and path_lines[i]:
                                        for line in path_lines[i]:
                                            line.remove()
                                        path_lines[i].clear()
                                    
                                    # 绘制完整路径
                                    line = ax.plot(xs, ys, linewidth=0.5, alpha=0.7, color=agent_colors[i])[0]
                                    path_lines[i].append(line)
                            
                            # 强制刷新画布
                            fig.canvas.draw_idle()
                            plt.pause(0.1)  # 短暂暂停确保渲染完成
                        except Exception as e:
                            print(f"渲染Levy路线时出错: {e}")
                    
                    # 完成渲染后，再终止模拟
                    if pbar is not None:
                        pbar.close()
                    break
                
                if actual_steps >= max_steps:
                    print(f"\n模拟完成（达到最大步数: {max_steps}）。")
                    if pbar is not None:
                        pbar.close()
                    break

    except Exception as main_e:
        # 捕获主循环异常并打印，继续进行清理与返回错误信息
        print(f"[Error] Simulation loop exception: {main_e}")
    finally:
        # 确保关闭图形和资源
        try:
            if fig is not None:
                plt.ioff()
                plt.close(fig)
        except Exception:
            pass
        # 强制回收
        gc.collect()

    # 非交互模式时绘制完整路径图（在主循环结束后）
    # ---- 在 run_simulation_fast 函数的非交互模式部分 ----
    # 修改这部分代码：
    try:
        if not show_interactive and ax is not None:
            print("Simulation completed, drawing all paths ..")

            # 为每个agent生成唯一颜色
            import matplotlib.cm as cm
            agent_colors = plt.cm.Set1(np.linspace(0, 1, len(agents)))
            
            if enable_global_simulation and GLOBAL_SIM_AVAILABLE:
                # 使用全球模拟路径绘制
                try:
                    print(f"使用全球模拟路径绘制agent数量: {len(agents)}")
                    # 创建颜色映射
                    color_map = {i: agent_colors[i] for i in range(len(agents))}
                    plot_global_paths(ax, agents, color_map)
                except Exception as e:
                    print(f"全球路径绘制错误: {e}")
                    # 全球模拟模式下禁用普通路径回退机制
            else:
                # 普通模拟模式或全球模拟不可用时，绘制普通路径
                for i, ag in enumerate(agents):
                    if len(ag.path) > 1:
                        sampled_path = ag.path[::10]
                        ys, xs = zip(*sampled_path)
                        ax.plot(xs, ys, linewidth=0.5, marker=None, alpha=0.6, color=agent_colors[i])
    except Exception as e:
        print(f"绘图错误: {e}")

    # 计算最终统计
    alive_count = sum(1 for a in agents if a.alive)
    lifespan_death_count = sum(1 for a in agents if not a.alive and a.death_type == "lifespan")
    supply_death_count = sum(1 for a in agents if not a.alive and a.death_type == "supply")
    bounds_death_count = sum(1 for a in agents if not a.alive and a.death_type == "out_of_bounds")

    # 最终标题（若图可用则更新）
    if ax is not None:
        try:
            if enable_lifespan_terminal:
                ax.set_title(f"Simulation Completed (Lifespan Terminal Mode, LEVY_EXP={levy_exp}) | "
                             f"Total Steps: {actual_steps} | Alive: {alive_count} | "
                             f"Lifespan Deaths: {lifespan_death_count} | Supply Deaths: {supply_death_count} | "
                             f"Bounds Deaths: {bounds_death_count}")
            else:
                if actual_steps < max_steps:
                    ax.set_title(
                        f"Simulation Early Terminated (LEVY_EXP={levy_exp}) | Steps: {actual_steps}/{max_steps} | "
                        f"Alive: {alive_count} | Lifespan Deaths: {lifespan_death_count} | "
                        f"Supply Deaths: {supply_death_count} | Bounds Deaths: {bounds_death_count}")
                else:
                    ax.set_title(f"Simulation Completed (LEVY_EXP={levy_exp}) | Total Steps: {max_steps} | "
                                 f"Alive: {alive_count} | Lifespan Deaths: {lifespan_death_count} | "
                                 f"Supply Deaths: {supply_death_count} | Bounds Deaths: {bounds_death_count}")
        except Exception:
            pass

    # 图内信息文本（安全调用）
    try:
        if ax is not None:
            mode_text = "Lifespan Terminal Mode" if enable_lifespan_terminal else "Step Limit Mode"
            ax.text(5, 5, f"Current Mode: {current_influence_mode_local} | Direction Mode: {direction_mode} | "
                          f"Lifespan Limit: {'Enabled' if ENABLE_LIFESPAN_LIMIT_local else 'Disabled'} | "
                          f"Simulation Mode: {mode_text} | LEVY_EXP: {levy_exp} | "
                          f"Steps Executed: {actual_steps}",
                    color='white', fontsize=8, ha='left', va='top',
                    bbox=dict(boxstyle='round', facecolor='black', alpha=0.5))
    except Exception:
        pass

    # 强制刷新画布（若存在）- 仅在show_interactive=True时执行
    try:
        if fig is not None and show_interactive:
            fig.canvas.draw()
    except Exception:
        pass

    # 显示交互窗口（调用工具脚本函数）- 根据show_interactive参数决定
    try:
        if show_interactive:  # 只有show_interactive为True时才显示
            show_interactive_window(fig, agents, actual_steps, max_steps, direction_seed, levy_seed, levy_exp,
                                  start_lat=start_lat_local, start_lon=start_lon_local, 
                                  self_speed=SELF_SPEED_local, direction_mode=direction_mode,
                                  current_influence_mode=current_influence_mode_local,
                                  enable_lifespan_limit=ENABLE_LIFESPAN_LIMIT_local,
                                  lifespan_years=LIFESPAN_YEARS_local,
                                  pure_full_state_survival_days=pure_full_state_survival_days,
                                  enable_b_supply=enable_b_supply,
                                  b_supply_percent=b_supply_percent,
                                  enable_global_simulation=enable_global_simulation,
                                  grid=grid,
                                  lats_inc=lats_inc,
                                  lons_inc=lons_inc,
                                  step_time_multiplier=step_time_multiplier,
                                  maximize_window=maximize_window,
                                  record_video=record_video)
        else:
            # 如果不显示交互窗口，直接关闭图形
            if fig is not None:
                plt.close(fig)
    except Exception:
        # 若在无 GUI 环境或 show_interactive_window 抛错，忽略
        pass

    # 自动导出结果（当不显示交互窗口时）
    if not show_interactive:
        print(f"自动导出结果，前缀: {export_prefix}")
        try:
            # 导入导出模块
            from simulation_utils import export_png, export_agent_data
            
            # 自动导出PNG图片
            export_png(agents, None, export_prefix=export_prefix)
            print(f"已导出PNG文件: {export_prefix}.png")
            
            # 自动导出Agent数据到Excel
            export_agent_data(agents, None, 
                            direction_seed=direction_seed, 
                            levy_seed=levy_seed, 
                            levy_exp=levy_exp, 
                            export_prefix=export_prefix,
                            start_lat=start_lat_local,
                            start_lon=start_lon_local,
                            self_speed=SELF_SPEED_local,
                            direction_mode=direction_mode,
                            current_influence_mode=current_influence_mode_local,
                            enable_lifespan_limit=ENABLE_LIFESPAN_LIMIT_local,
                            lifespan_years=LIFESPAN_YEARS_local,
                            pure_full_state_survival_days=pure_full_state_survival_days,
                            enable_b_supply=enable_b_supply,
                            b_supply_percent=b_supply_percent,
                            enable_global_simulation=enable_global_simulation,
                            n_agents=n_agents,
                            max_steps=max_steps,
                            actual_steps=actual_steps,
                            grid=grid,
                            lats_inc=lats_inc,
                            lons_inc=lons_inc,
                            step_time_multiplier=step_time_multiplier)
            print(f"已导出Excel文件: {export_prefix}.xlsx")
        except Exception as e:
            print(f"自动导出结果时出错: {e}")
    
    # 释放视频写入器
    if video_writer is not None:
        video_writer.release()
        print("视频录制已完成，文件已保存")
    
    gc.collect()

    # 构建 summary 并返回（便于 UI 进一步处理）
    summary = {
        "agents": agents,
        "steps_executed": actual_steps,
        "n_agents": n_agents,
        "alive_count": alive_count,
        "lifespan_death_count": lifespan_death_count,
        "supply_death_count": supply_death_count,
        "bounds_death_count": bounds_death_count,
        "direction_seed": direction_seed,
        "levy_seed": levy_seed,
        "levy_exp": levy_exp,
        "direction_mode": direction_mode,
        "current_influence_mode": current_influence_mode_local
    }

    # 强制关闭所有图形资源
    try:
        plt.close('all')
        # 如果使用了Tkinter后端，尝试关闭Tk根窗口
        if 'Tk' in plt.get_backend():
            import tkinter as tk
            for widget in tk._default_root.winfo_children():
                widget.destroy()
    except Exception:
        pass

    # 强制垃圾回收
    gc.collect()
    return summary


# ---- 主入口（用于核心逻辑测试） ------------------------------------------------------
if __name__ == "__main__":
    # 强制设置matplotlib后端为TkAgg，避免交互冲突
    plt.switch_backend('TkAgg')
    # 可直接调用模拟函数测试核心功能，示例：
    # run_simulation_fast(
    #     excel_path="merged_result.xlsx",  # 替换为你的地图文件路径
    #     n_agents=500,
    #     max_steps=100000,
    #     temp_path="temperature.xlsx",  # 加权模式需提供温度文件
    #     levy_exp=LEVY_EXP_PRIMARY,
    #     enable_lifespan_terminal=False
    # )
    pass