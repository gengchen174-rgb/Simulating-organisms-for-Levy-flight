"""
全球模拟工具函数
包含处理全球模拟的坐标标准化、方向调整和路径绘制功能

全新设计的坐标系统解决方案
=========================
问题分析：
- 当agent从西经180度向西移动时，系统错误地在西经180度与东经180度之间绘制直线
- 根本原因：使用-180/180经度范围导致的边界不连续性

解决方案：
1. 内部使用360度经度范围(0-360)避免边界问题
2. 实现智能路径分段检测
3. 绘图时动态转换为-180/180坐标

算法设计：
- normalize_coordinates: 将任意坐标转换为-180/180经度范围
- GlobalPathManager: 内部使用360度坐标管理路径，绘图时转换
- 路径分段：基于实际地球距离判断是否需要分段

集成方案：
- 保持与现有API兼容
- 无需修改调用代码
- 提供向后兼容的接口
"""
from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional
from simulation_constants import MIN_LON, MAX_LON, MIN_LAT, MAX_LAT


def normalize_coordinates(lon: float, lat: float) -> Tuple[float, float]:
    """
    经纬度坐标标准化函数
    
    算法设计：
    1. 处理纬度过极问题，支持多次穿过极点
    2. 将经度标准化到[-180, 180]范围
    3. 精确处理边界条件
    
    参数:
        lon: 经度（度）
        lat: 纬度（度）
    
    返回:
        tuple: (标准化经度, 标准化纬度)
    """
    EPSILON = 1e-10

    # 处理纬度过极(可能多次穿过极点)
    while lat > 90 or lat < -90:
        if lat > 90:  # 过北极
            lat = 180 - lat  # 纬度反向计算
            lon += 180  # 经度增加180度，相当于东西反转
        elif lat < -90:  # 过南极
            lat = -180 - lat  # 纬度反向计算(lat为负数)
            lon += 180  # 经度增加180度，相当于东西反转

    # 确保纬度在[-90, 90]范围内
    lat = max(-90, min(90, lat))

    # 处理数值误差
    if abs(lat - 90) < EPSILON:
        lat = 90
    elif abs(lat + 90) < EPSILON:
        lat = -90

    # 经度标准化到[-180, 180]范围
    lon = lon % 360  # 映射到[0, 360)
    
    # 将[0, 360)转换为[-180, 180)
    if lon >= 180:
        lon -= 360

    # 处理经度的数值误差
    if abs(lon - 180) < EPSILON:
        lon = 180
    elif abs(lon + 180) < EPSILON:
        lon = -180

    return lon, lat


def adjust_direction_for_pole_crossing(start_lat, end_lat, current_alpha):
    """
    调整穿越极点后的移动方向
    """
    # 检查是否穿越极点
    if (start_lat <= 90 and end_lat > 90) or (start_lat >= -90 and end_lat < -90):
        # 穿越极点，方向反转（加180度）
        adjusted_alpha = (current_alpha + 180) % 360
        return adjusted_alpha
    return current_alpha


def get_wrap_around_offset(lon1, lon2):
    """
    检测经度跨越并返回绘图偏移量
    """
    # 计算两个点之间的直接距离和绕地球一圈的距离
    direct_diff = abs(lon1 - lon2)
    wrap_diff = 360 - direct_diff
    
    # 如果绕地球一圈的距离更短，说明跨越了日期变更线
    if wrap_diff < direct_diff:
        # 确定跨越方向
        # 从西向东跨越（如从170°到-170°）
        if (lon1 > 0 and lon2 < 0) and (lon1 - lon2 > 180):
            return -360
        # 从东向西跨越（如从-170°到170°）
        elif (lon1 < 0 and lon2 > 0) and (lon2 - lon1 > 180):
            return 360
        # 特殊情况：从180°向西到-170°
        elif lon1 == 180 and lon2 < 0:
            return 360
        # 特殊情况：从-180°向东到170°
        elif lon1 == -180 and lon2 > 0:
            return -360
        elif lon1 < lon2:
            return -360  # 从西向东跨越
        else:
            return 360  # 从东向西跨越
    return 0
    
    # 如果绕地球一圈的距离更短，说明跨越了日期变更线
    if wrap_diff < direct_diff:
        # 确定跨越方向
        # 注意：lon1和lon2都是标准化后的坐标（-180到180）
        # 但由于normalize_coordinates将-180转换为180，所以需要特殊处理
        
        # 特殊情况：从180°向西到170°（实际是-190°标准化后）
        if lon1 == 180 and lon2 < 0:
            return 360  # 从东向西跨越
        # 特殊情况：从-180°（标准化为180°）向东到-170°
        elif lon2 == 180 and lon1 < 0:
            return -360  # 从西向东跨越
        elif lon1 < lon2:
            return -360  # 从西向东跨越
        else:
            return 360  # 从东向西跨越
    return 0


class GlobalPathManager:
    """管理全球模拟中的路径分段和绘制
    
    全新设计的路径管理系统，彻底解决跨180度经度边界时的错误连接线问题
    核心算法：
    1. 使用360度经度范围（0-360）进行内部坐标管理，避免-180/180边界问题
    2. 智能路径分段检测，基于实际地球距离判断是否需要分段
    3. 绘图时动态转换为-180/180坐标，确保地图显示正确
    """

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.segments: List[List[Tuple[float, float]]] = []  # 存储360度范围的坐标
        self.current_segment: List[Tuple[float, float]] = []
        self.last_lon_360: Optional[float] = None  # 存储0-360范围内的经度
        self.last_lat: Optional[float] = None

    def _normalize_to_360(self, lon: float, lat: float) -> Tuple[float, float]:
        """
        将坐标标准化到360度经度范围（0-360）和-90到90度纬度范围
        """
        # 处理纬度
        while lat > 90 or lat < -90:
            if lat > 90:  # 过北极
                lat = 180 - lat
                lon += 180
            elif lat < -90:  # 过南极
                lat = -180 - lat
                lon += 180
        
        # 确保纬度在[-90, 90]范围内
        lat = max(-90, min(90, lat))
        
        # 处理经度到0-360范围
        lon = lon % 360
        
        return lon, lat

    def add_point(self, lon: float, lat: float) -> None:
        """
        添加路径点，使用全新的360度坐标管理系统
        """
        # 使用360度经度范围进行内部坐标管理
        lon_360, norm_lat = self._normalize_to_360(lon, lat)

        # 如果是第一个点，直接添加
        if self.last_lon_360 is None:
            self.current_segment.append((lon_360, norm_lat))
            self.last_lon_360 = lon_360
            self.last_lat = norm_lat
            return

        # 检查是否需要分段
        # 1. 检查是否跨越极点（纬度差接近180度）
        pole_crossed = abs(self.last_lat - norm_lat) > 170
        
        # 2. 检查是否跨越了180度经线
        # 在360度系统中，跨越180度经线的情况是：
        # - 从接近0度突然增大到接近360度（从东向西跨越）
        # - 从接近360度突然减小到接近0度（从西向东跨越）
        wrap_crossed = False
        
        # 计算经度差
        lon_diff = lon_360 - self.last_lon_360
        
        # 检测跨越180度经线的情况
        # 当经度差超过180度或小于-180度时，说明跨越了180度经线
        if lon_diff > 180 or lon_diff < -180:
            wrap_crossed = True
        
        # 另外，当当前经度和上一个经度分别在180度经线的两侧时，也说明跨越了180度经线
        # 例如：上一个经度是170度（西经170度），当前经度是190度（东经170度）
        elif (self.last_lon_360 < 180 and lon_360 > 180) or (self.last_lon_360 > 180 and lon_360 < 180):
            wrap_crossed = True

        if pole_crossed or wrap_crossed:
            # 保存当前分段，不添加额外的边界点
            if len(self.current_segment) > 0:
                self.segments.append(self.current_segment.copy())
            
            # 开始新的分段，直接添加新的点，不添加额外的边界点
            self.current_segment = [(lon_360, norm_lat)]
        else:
            # 添加到当前分段
            self.current_segment.append((lon_360, norm_lat))

        self.last_lon_360 = lon_360
        self.last_lat = norm_lat

    def finalize(self) -> None:
        """结束当前分段"""
        if self.current_segment:
            self.segments.append(self.current_segment.copy())
        self.current_segment = []

    def get_paths_for_plotting(self) -> List[Tuple[List[float], List[float]]]:
        """
        获取用于绘制的路径数据，转换为-180/180经度范围
        
        核心转换逻辑：
        1. 将360度经度转换为-180/180经度
        2. 确保每个分段内的经度是连续的
        """
        self.finalize()
        paths = []
        
        for segment in self.segments:
            if not segment:
                continue
                
            # 将360度经度转换为-180/180经度
            plot_lons = []
            plot_lats = []
            
            for lon_360, lat in segment:
                # 转换为-180/180经度
                lon_180 = lon_360 - 360 if lon_360 > 180 else lon_360
                plot_lons.append(lon_180)
                plot_lats.append(lat)
            
            paths.append((plot_lons, plot_lats))
        
        return paths


def plot_global_paths(ax, agents, color_map=None):
    """
    绘制全球模拟的路径
    """
    from matplotlib.colors import to_rgba
    import matplotlib.cm as cm

    # 如果没有提供颜色映射，为每个agent生成唯一颜色
    if not color_map:
        agent_colors = plt.cm.Set1(np.linspace(0, 1, len(agents)))
        color_map = {i: agent_colors[i] for i in range(len(agents))}

    for i, agent in enumerate(agents):
        if not hasattr(agent, 'global_path_manager') or not agent.global_path_manager:
            continue

        # 确定颜色 - 优先使用颜色映射
        if i in color_map:
            color = color_map[i]
        elif agent.alive:
            color = 'green'
        elif agent.death_type == "lifespan":
            color = 'orange'
        elif agent.death_type == "supply":
            color = 'red'
        else:
            color = 'gray'

        # 获取路径分段
        paths = agent.global_path_manager.get_paths_for_plotting()
        for path_lons, path_lats in paths:
            if len(path_lons) > 1:
                ax.plot(path_lons, path_lats, color=color, linewidth=0.5, alpha=0.7)


def update_agent_for_global_simulation(agent, new_lat, new_lon, alpha):
    """
    更新Agent的坐标和方向（全球模拟版本）
    """
    # 调整方向（如果穿越极点）
    adjusted_alpha = adjust_direction_for_pole_crossing(agent.lat, new_lat, alpha)

    # 标准化坐标
    norm_lon, norm_lat = normalize_coordinates(new_lon, new_lat)

    # 更新Agent路径
    if not hasattr(agent, 'global_path_manager'):
        agent.global_path_manager = GlobalPathManager(id(agent))

    agent.global_path_manager.add_point(new_lon, new_lat)

    return norm_lat, norm_lon, adjusted_alpha


def check_global_boundary(lat: float, lon: float, grid, lats_inc, lons_inc, nrows: int) -> bool:
    """
    检查坐标是否在有效范围内（全球模拟版本）
    全球模拟中，所有坐标都是有效的，只需要标准化
    """
    return True