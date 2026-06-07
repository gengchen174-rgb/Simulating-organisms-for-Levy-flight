"""
自动化实验执行器 - 核心逻辑模块
负责实验执行、参数解析、文件处理等核心功能
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys
import os
import ctypes
from ctypes import wintypes
import time
import threading
import queue
from main_200 import (
    save_config, run_simulation_fast,
    DEFAULT_CONFIG, MIN_LAT, MAX_LAT, MIN_LON, MAX_LON,
    disabled_directions, LEVY_EXP_PRIMARY, LEVY_EXP_SECONDARY,
    get_grid_index  # 添加缺失的函数导入
)
from simulation_utils import load_map, locate_cell


class AutomatedExperimentCore:
    """自动化实验执行器核心逻辑类"""
    
    def __init__(self):
        """初始化核心逻辑模块"""
        self.automation_file_path = None
        self.experiment_data = None
        self.current_experiment_index = 0
        self.terminal_log_file = None
        self.original_stdout = None
        self.original_stderr = None
        self.event_log_file = None
        
        # 初始化终端日志记录
        self.init_terminal_logging()
    
    def init_terminal_logging(self):
        """初始化终端日志记录"""
        try:
            # 创建终端日志文件
            self.terminal_log_file = os.path.join(os.getcwd(), "terminal_output.log")
            
            # 保存原始stdout和stderr
            self.original_stdout = sys.stdout
            self.original_stderr = sys.stderr
            
            # 创建过滤输出流
            sys.stdout = self.FilteredStream(self.original_stdout, self.terminal_log_file)
            sys.stderr = self.FilteredStream(self.original_stderr, self.terminal_log_file)
            
            self.log("终端日志记录已初始化")
        except Exception as e:
            print(f"初始化终端日志失败: {e}")
    
    class FilteredStream:
        """过滤输出流，用于分离终端显示和日志文件"""
        
        def __init__(self, original_stream, log_file):
            self.original_stream = original_stream
            self.log_file = log_file
            self.buffer = ""
            
        def write(self, text):
            """写入文本，过滤进度条等不需要记录到文件的内容"""
            # 始终输出到原始流（终端显示）
            self.original_stream.write(text)
            self.original_stream.flush()
            
            # 添加到缓冲区
            self.buffer += text
            
            # 检查是否包含换行符
            if '\n' in text:
                lines = self.buffer.split('\n')
                # 保留最后一行（可能不完整）
                self.buffer = lines[-1]
                
                # 处理完整的行
                for line in lines[:-1]:
                    if not self._is_progress_line(line):
                        self._write_to_log_file(line + '\n')
        
        def flush(self):
            """刷新缓冲区"""
            self.original_stream.flush()
            
            # 如果缓冲区有内容且不是进度条，写入日志文件
            if self.buffer and not self._is_progress_line(self.buffer):
                self._write_to_log_file(self.buffer)
                self.buffer = ""
        
        def _is_progress_line(self, line):
            """判断是否为进度条行"""
            progress_indicators = [
                'Simulation Progress:',
                '|',
                'step/s',
                '%',
                '█',
                '▓',
                '▒',
                '░'
            ]
            return any(indicator in line for indicator in progress_indicators)
        
        def _is_critical_info(self, line):
            """判断是否为关键信息（需要记录到日志文件）"""
            critical_keywords = [
                'ERROR', '错误', '失败', 'Exception', 'Traceback',
                '成功', '完成', '导出', '执行', '模拟',
                '实验组', '配置文件', '双Levy模式'
            ]
            return any(keyword in line for keyword in critical_keywords)
        
        def _write_to_log_file(self, text):
            """写入日志文件"""
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(text)
            except Exception as e:
                # 如果写入失败，静默处理，避免循环错误
                pass
    
    def save_terminal_log(self):
        """保存终端日志"""
        try:
            if hasattr(sys.stdout, 'flush'):
                sys.stdout.flush()
            if hasattr(sys.stderr, 'flush'):
                sys.stderr.flush()
            self.log("终端日志已保存")
        except Exception as e:
            print(f"保存终端日志失败: {e}")
    
    def cleanup_terminal_logging(self):
        """清理终端日志记录"""
        try:
            # 保存最终日志
            self.save_terminal_log()
            
            # 恢复原始stdout和stderr
            if hasattr(self, 'original_stdout') and self.original_stdout:
                sys.stdout = self.original_stdout
            if hasattr(self, 'original_stderr') and self.original_stderr:
                sys.stderr = self.original_stderr
            
            self.log("终端日志记录已清理")
        except Exception as e:
            print(f"清理终端日志失败: {e}")
    
    def log(self, message):
        """添加日志信息 - 同时打印到PowerShell终端和写入日志文件"""
        # 获取当前时间戳
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        
        # 直接打印到控制台（PowerShell终端）
        print(log_message)
        
        # 写入日志文件
        try:
            if self.terminal_log_file:
                with open(self.terminal_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_message + '\n')
                    f.flush()  # 立即刷新缓冲区，确保数据写入
        except Exception as e:
            # 如果写入失败，只打印到控制台
            print(f"[ERROR] 写入日志文件失败: {e}")

    def check_coordinate_validity(self, lat, lon, map_path, enable_global_simulation=False):
        """检查坐标是否为陆地Y区域，返回True表示合法（非陆地），False表示非法（陆地）"""
        try:
            # 加载地图
            grid = load_map(map_path)
            nrows, ncols = grid.shape
            
            # 生成经纬度分割
            lats_inc = np.linspace(MIN_LAT, MAX_LAT, nrows + 1)
            lons_inc = np.linspace(MIN_LON, MAX_LON, ncols + 1)
            
            # 检查初始位置是否超出地图网格范围
            start_idx = get_grid_index(lat, lon, lats_inc, lons_inc, nrows, enable_global_simulation)
            if not start_idx:
                self.log(f"坐标检查: 位置({lat}, {lon})超出地图网格范围，Agent可能无法移动")
                return True  # 不跳过实验，只是警告
            
            # 定位单元格（使用与实际模拟相同的enable_global_simulation参数）
            cell = locate_cell(lat, lon, grid, lats_inc, lons_inc, enable_global_simulation=enable_global_simulation)
            
            if cell is not None:
                # 检查单元格类型
                if cell.cell_type == "Y":
                    self.log(f"坐标检查: 位置({lat}, {lon})为陆地Y区域，非法位置")
                    return False
                elif cell.cell_type not in ("B", "G"):
                    self.log(f"坐标检查: 位置({lat}, {lon})为未知类型({cell.cell_type})，可能影响移动")
                    return True  # 不跳过实验，只是警告
                else:
                    self.log(f"坐标检查: 位置({lat}, {lon})为{cell.cell_type}区域，合法位置")
                    return True
            else:
                # 如果无法定位单元格，默认为合法位置
                self.log(f"坐标检查: 位置({lat}, {lon})无法定位单元格，默认为合法位置")
                return True
                
        except Exception as e:
            self.log(f"坐标检查失败: {e}，默认为合法位置")
            return True
    
    def execute_all_experiments(self, ui_queue, update_progress_func):
        """执行所有实验 - 核心执行逻辑"""
        try:
            # 在日志第一行打印导入的文件名称
            file_name = Path(self.automation_file_path).name
            self.log(f"=== 导入配置文件: {file_name} ===")
            
            # 确保result文件夹存在（使用脚本所在目录）
            script_dir = os.path.dirname(os.path.abspath(__file__))
            result_dir = os.path.join(script_dir, "result")
            if not os.path.exists(result_dir):
                os.makedirs(result_dir)
            
            # 初始化事件日志文件 - 修改为保存在result文件夹中
            self.event_log_file = os.path.join(result_dir, "experiment_event.log")
            with open(self.event_log_file, "w", encoding="utf-8") as f:
                import datetime
                f.write(f"# 实验事件日志 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 配置文件: {self.automation_file_path}\n")
                f.write("# 格式: 时间|实验组索引|导出前缀|事件类型|详细信息\n")
            
            # 合并文件信息日志
            self.log(f"结果目录: {result_dir}")
            self.log(f"事件日志: {self.event_log_file}")
            
            # 读取配置文件
            self.log("正在读取配置文件...")
            
            # 根据文件扩展名选择读取方式
            file_extension = Path(self.automation_file_path).suffix.lower()
            if file_extension == '.csv':
                self.experiment_data = pd.read_csv(self.automation_file_path)
                self.log("CSV格式配置文件读取完成")
            elif file_extension == '.xlsx':
                self.experiment_data = pd.read_excel(self.automation_file_path)
                self.log("Excel格式配置文件读取完成")
            else:
                # 默认尝试CSV格式
                self.experiment_data = pd.read_csv(self.automation_file_path)
                self.log("未知格式，CSV读取完成")
            
            self.current_experiment_index = 0
            
            total_experiments = len(self.experiment_data)
            self.log(f"实验配置数量: {total_experiments}")
            
            # 开始执行实验
            for i in range(total_experiments):
                if hasattr(self, 'stop_requested') and self.stop_requested:
                    self.log("用户请求停止执行")
                    break
                
                # 更新进度
                progress = (i / total_experiments) * 100
                ui_queue.put(lambda: update_progress_func(progress, f"正在执行实验组 {i+1}/{total_experiments}"))
                
                # 执行当前实验组
                self.current_experiment_index = i
                self._execute_next_experiment()
            
            # 所有实验完成
            ui_queue.put(lambda: update_progress_func(100, "所有实验执行完成"))
            self.log("所有实验已执行完成！")
            
        except Exception as e:
            self.log(f"执行过程中出错: {e}")
            raise
    
    def _execute_next_experiment(self):
        """执行下一组实验"""
        try:
            experiment_row = self.experiment_data.iloc[self.current_experiment_index]
            
            # 解析实验参数
            params = self.parse_experiment_params(experiment_row)
            
            self.log(f"=== 实验组 {self.current_experiment_index + 1}: {params.get('export_prefix', '未知')} ===")
            
            # 检查坐标合法性
            start_lat = params.get('start_lat')
            start_lon = params.get('start_lon')
            map_path = params.get('map_path')
            enable_global_simulation = params.get('enable_global_simulation', True)
            direction_mode = params.get('direction_mode')
            temp_path = params.get('temp_path')
            
            # 验证地图文件存在性（直接使用配置文件中的路径）
            if map_path is not None:
                # 直接使用配置文件中的路径，不进行路径修正
                if not Path(map_path).exists():
                    error_msg = f"地图文件不存在: {map_path}"
                    self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                                  "ERROR", error_msg)
                    self.log(f"[ERROR] {error_msg}")
                    return  # 直接返回，不执行模拟
                else:
                    self.log(f"地图文件: {map_path}")
            
            # 地图尺寸检测和显示
            try:
                df_map = pd.read_excel(map_path, header=None)
                map_nrows, map_ncols = df_map.shape
                self.log(f"地图尺寸: {map_nrows} × {map_ncols}")
            except Exception as e:
                error_msg = f"读取地图文件失败: {e}"
                self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                              "ERROR", error_msg)
                self.log(f"[ERROR] {error_msg}")
                return  # 直接返回，不执行模拟
            
            # 验证坐标合法性
            if start_lat is not None and start_lon is not None and map_path is not None:
                is_valid_coordinate = self.check_coordinate_validity(start_lat, start_lon, map_path, enable_global_simulation)
                
                if not is_valid_coordinate:
                    # 坐标非法，跳过该实验
                    self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                                  "SKIP", f"坐标非法，跳过实验: 位置({start_lat}, {start_lon})为陆地Y区域")
                    self.log(f"[SKIP] 坐标非法，跳过实验")
                    return  # 直接返回，不执行模拟
            
            # 记录实验开始事件
            self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                          "START", "实验开始执行")
            
            # 执行模拟
            success = self.run_simulation(params)
            
            if success:
                self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                              "SUCCESS", "实验执行成功")
                self.log(f"[SUCCESS] 实验执行完成")
            else:
                self.log_event(self.current_experiment_index, params.get('export_prefix', '未知'), 
                              "ERROR", "实验执行失败")
                self.log(f"[ERROR] 实验执行失败")
            
            # 实验完成后，清理操作已经在run_simulation内部完成，这里不需要重复清理
            self.log(f"实验组 {self.current_experiment_index + 1} 完成")
            
        except Exception as e:
            error_msg = f"执行实验组 {self.current_experiment_index + 1} 时出错: {e}"
            self.log(f"[ERROR] {error_msg}")
            self.log_event(self.current_experiment_index, "N/A", "ERROR", error_msg)
            self.log(f"[INFO] 跳过当前实验组，继续执行下一个")
            # 不抛出异常，直接返回，继续执行下一个实验组
    
    def _get_param_with_priority(self, row, param_name, default_value):
        """
        获取参数值，确保CSV/XLSX参数优先于默认值
        
        Args:
            row: 实验数据行
            param_name: 参数名
            default_value: 默认值
            
        Returns:
            参数值（CSV/XLSX中的值优先，只有在参数确实缺失时才使用默认值）
        """
        # 检查参数是否存在
        if param_name not in row:
            return default_value
        
        # 获取参数值
        value = row[param_name]
        
        # 检查是否为有效值（非空、非NaN、非空字符串）
        if pd.isna(value) or value == '' or value == 'None':
            # 参数存在但为空，使用默认值
            return default_value
        
        # 参数存在且有有效值，使用CSV/XLSX中的值
        return value

    def parse_experiment_params(self, experiment_row):
        """解析实验参数"""
        
        def yes_no_to_bool(value):
            """将'yes'/'no'转换为布尔值"""
            if isinstance(value, str):
                value = value.strip().lower()
                if value in ['yes', 'y', 'true', '1', '是']:
                    return True
                elif value in ['no', 'n', 'false', '0', '否']:
                    return False
            return bool(value)
        
        def parse_seed(seed_value):
            """解析种子值"""
            if pd.isna(seed_value) or seed_value == '' or seed_value == 'None':
                return None
            try:
                return int(seed_value)
            except (ValueError, TypeError):
                return None
        
        params = {}
        
        # 定义所有必需参数的默认值（与simulation_constants.py中的DEFAULT_CONFIG保持一致）
        EXPERIMENT_DEFAULTS = {
            # 基本参数
            'ExportPrefix': f'experiment_{self.current_experiment_index + 1}',
            'MapPath': 'map/205.xlsx',
            'NAgents': 200,  # 与DEFAULT_CONFIG中的number_of_agents一致
            'MaxSteps': 100000,  # 与DEFAULT_CONFIG中的max_steps一致
            
            # 布尔参数
            'EnableLifespanTerminal': False,  # 与DEFAULT_CONFIG中的enable_lifespan_terminal一致
            'EnableGlobalSimulation': True,  # 与DEFAULT_CONFIG中的ENABLE_GLOBAL_SIMULATION一致
            'EnableBSupply': False,  # 与DEFAULT_CONFIG中的enable_b_supply一致
            'EnableLifespanLimit': False,  # 与DEFAULT_CONFIG中的enable_lifespan_limit一致
            
            # 数值参数
            'BSupplyPercent': 50.0,  # 与DEFAULT_CONFIG中的b_supply_percent一致
            'StartLat': 20.0,  # 与DEFAULT_CONFIG中的start_lat一致
            'StartLon': 100.0,  # 与DEFAULT_CONFIG中的start_lon一致
            'SelfSpeed': 3.0,  # 与DEFAULT_CONFIG中的self_speed一致
            'PureSurvivalDays': 10.0,  # 与DEFAULT_CONFIG中的pure_full_state_survival_days一致
            'LifespanYears': 30.0,  # 与DEFAULT_CONFIG中的lifespan_years一致
            
            # 模式参数
            'DirectionMode': 'weighted',  # 与DEFAULT_CONFIG中的direction_mode一致
            'CurrentInfluenceMode': 'with_current',  # 与DEFAULT_CONFIG中的current_influence_mode一致
            
            # 双Levy模式
            'DualLevyMode': 'no'  # 与DEFAULT_CONFIG中的enable_dual_levy一致
        }
        
        # 解析基本参数 - 确保CSV/XLSX参数优先
        params['export_prefix'] = self._get_param_with_priority(experiment_row, 'ExportPrefix', EXPERIMENT_DEFAULTS['ExportPrefix'])
        
        # 自动推断地图路径：优先处理MapType参数
        map_type_from_config = self._get_param_with_priority(experiment_row, 'MapType', '')
        map_path_from_config = self._get_param_with_priority(experiment_row, 'MapPath', '')
        
        # 优先使用MapType参数（如"245" -> "map/245.xlsx"）
        if map_type_from_config and map_type_from_config != '':
            # 清理MapType值（去除空格等）
            map_type_clean = str(map_type_from_config).strip()
            params['map_path'] = f'map/{map_type_clean}.xlsx'
            self.log(f"使用MapType参数: '{map_type_from_config}' -> 地图路径: {params['map_path']}")
        # 其次使用MapPath参数（直接路径）
        elif map_path_from_config and map_path_from_config != '':
            params['map_path'] = map_path_from_config
            self.log(f"使用MapPath参数: {params['map_path']}")
        else:
            # 从物种名称中提取年份（如 "Helveticosaurus zollingeri-245" -> "245"）
            species_name = params['export_prefix']
            if '-' in species_name:
                year_part = species_name.split('-')[-1]
                if year_part.isdigit():
                    params['map_path'] = f'map/{year_part}.xlsx'
                    self.log(f"从物种名称推断地图路径: {params['map_path']}")
                else:
                    params['map_path'] = EXPERIMENT_DEFAULTS['MapPath']
                    self.log(f"使用默认地图路径: {params['map_path']}")
            else:
                params['map_path'] = EXPERIMENT_DEFAULTS['MapPath']
                self.log(f"使用默认地图路径: {params['map_path']}")
        
        params['n_agents'] = int(self._get_param_with_priority(experiment_row, 'NAgents', EXPERIMENT_DEFAULTS['NAgents']))
        params['max_steps'] = int(self._get_param_with_priority(experiment_row, 'MaxSteps', EXPERIMENT_DEFAULTS['MaxSteps']))
        
        # 解析种子参数
        params['direction_seed'] = parse_seed(experiment_row.get('DirectionSeed'))
        params['levy_seed'] = parse_seed(experiment_row.get('LevySeed'))
        
        # 解析布尔参数
        params['enable_lifespan_terminal'] = yes_no_to_bool(self._get_param_with_priority(experiment_row, 'EnableLifespanTerminal', EXPERIMENT_DEFAULTS['EnableLifespanTerminal']))
        params['enable_global_simulation'] = yes_no_to_bool(self._get_param_with_priority(experiment_row, 'EnableGlobalSimulation', EXPERIMENT_DEFAULTS['EnableGlobalSimulation']))
        params['enable_b_supply'] = yes_no_to_bool(self._get_param_with_priority(experiment_row, 'EnableBSupply', EXPERIMENT_DEFAULTS['EnableBSupply']))
        params['enable_lifespan_limit'] = yes_no_to_bool(self._get_param_with_priority(experiment_row, 'EnableLifespanLimit', EXPERIMENT_DEFAULTS['EnableLifespanLimit']))
        
        # 解析数值参数（不使用JSON配置）
        params['b_supply_percent'] = float(self._get_param_with_priority(experiment_row, 'BSupplyPercent', EXPERIMENT_DEFAULTS['BSupplyPercent']))
        params['start_lat'] = float(self._get_param_with_priority(experiment_row, 'StartLat', EXPERIMENT_DEFAULTS['StartLat']))
        params['start_lon'] = float(self._get_param_with_priority(experiment_row, 'StartLon', EXPERIMENT_DEFAULTS['StartLon']))
        params['self_speed'] = float(self._get_param_with_priority(experiment_row, 'SelfSpeed', EXPERIMENT_DEFAULTS['SelfSpeed']))
        params['pure_survival_days'] = float(self._get_param_with_priority(experiment_row, 'PureSurvivalDays', EXPERIMENT_DEFAULTS['PureSurvivalDays']))
        params['lifespan_years'] = float(self._get_param_with_priority(experiment_row, 'LifespanYears', EXPERIMENT_DEFAULTS['LifespanYears']))
        
        # 验证参数范围（与ui_selector.py一致）
        if not (MIN_LAT <= params['start_lat'] <= MAX_LAT):
            self.log(f"警告：纬度必须在{MIN_LAT}和{MAX_LAT}之间，当前值：{params['start_lat']}")
            params['start_lat'] = max(MIN_LAT, min(MAX_LAT, params['start_lat']))
        
        if not (MIN_LON <= params['start_lon'] <= MAX_LON):
            self.log(f"警告：经度必须在{MIN_LON}和{MAX_LON}之间，当前值：{params['start_lon']}")
            params['start_lon'] = max(MIN_LON, min(MAX_LON, params['start_lon']))
        
        if params['self_speed'] <= 0:
            self.log(f"警告：自身速度必须为正数，当前值：{params['self_speed']}，将使用默认值")
            params['self_speed'] = EXPERIMENT_DEFAULTS['SelfSpeed']
        
        # 解析模式参数
        params['direction_mode'] = self._get_param_with_priority(experiment_row, 'DirectionMode', EXPERIMENT_DEFAULTS['DirectionMode'])
        params['current_influence_mode'] = self._get_param_with_priority(experiment_row, 'CurrentInfluenceMode', EXPERIMENT_DEFAULTS['CurrentInfluenceMode'])
        
        # 解析双Levy模式
        dual_levy_raw = self._get_param_with_priority(experiment_row, 'DualLevyMode', EXPERIMENT_DEFAULTS['DualLevyMode'])
        params['dual_levy_mode'] = yes_no_to_bool(dual_levy_raw)
        self.log(f"双Levy模式解析: raw_value='{dual_levy_raw}', bool_value={params['dual_levy_mode']}")
        
        # 直接禁用温度权重模式：强制使用random模式
        if params['direction_mode'] == 'weighted':
            self.log(f"[INFO] 温度权重模式已禁用，强制使用随机模式")
            params['direction_mode'] = 'random'
        
        # 设置temp_path：random模式下为None
        params['temp_path'] = None
        
        self.log(f"方向模式: {params['direction_mode']}, TempPath: {params['temp_path']}")
        
        return params
    
    def run_simulation(self, params):
        """执行单次模拟"""
        try:
            # 检查是否启用双Levy模式
            dual_levy_mode = params.get('dual_levy_mode', False)
            
            if dual_levy_mode:
                self.log(f"使用双Levy模式，将执行两次模拟 (dual_levy_mode={dual_levy_mode}, type={type(dual_levy_mode)})")
                
                # 第一次模拟（主要Levy指数）
                self.log("执行第一次模拟 (LEVY_EXP_PRIMARY)...")
                
                # 使用try-except包装模拟执行，防止崩溃
                try:
                    # 正确计算 max_life_seconds
                    if params["enable_lifespan_limit"]:
                        max_life_seconds = params["lifespan_years"] * 365 * 24 * 3600
                    else:
                        max_life_seconds = 0
                    
                    run_simulation_fast(
                        excel_path=params["map_path"],
                        n_agents=params["n_agents"],
                        max_steps=params["max_steps"],
                        direction_seed=params["direction_seed"],
                        levy_seed=params["levy_seed"],
                        temp_path=params["temp_path"],
                        levy_exp=LEVY_EXP_PRIMARY,
                        enable_lifespan_terminal=params["enable_lifespan_terminal"],
                        max_life_seconds=max_life_seconds,
                        direction_mode=params["direction_mode"],
                        show_interactive=False,  # 确保非交互模式
                        enable_global_simulation=params["enable_global_simulation"],
                        export_prefix=f"{params['export_prefix']}_1",
                        enable_b_supply=params["enable_b_supply"],
                        b_supply_percent=params["b_supply_percent"],
                        start_lat=params["start_lat"],
                        start_lon=params["start_lon"],
                        self_speed=params["self_speed"],
                        pure_survival_days=params["pure_survival_days"],
                        current_influence_mode=params["current_influence_mode"],
                        enable_lifespan_limit=params["enable_lifespan_limit"],
                        lifespan_years=params["lifespan_years"],
                        verbose_params=True  # 第一次模拟打印完整参数信息
                    )
                except Exception as e:
                    self.log(f"第一次模拟执行失败: {e}")
                    # 尝试清理资源后继续
                    self._cleanup_after_simulation()
                    return False
                
                # 检查第一次模拟导出状态
                export_prefix_1 = f"{params['export_prefix']}_1"
                png_file_1 = f"{export_prefix_1}.png"
                excel_file_1 = f"{export_prefix_1}.xlsx"
                
                # 如果导出文件不存在，等待导出完成（但不要无限等待）
                export_timeout = 60  # 最多等待60秒
                if not self.wait_for_export_completion(png_file_1, excel_file_1, timeout=export_timeout):
                    self.log(f"第一次模拟导出超时（超过{export_timeout}秒），继续执行第二次模拟")
                
                # 执行轻量级清理，避免删除必要的模块
                self.log("执行轻量级清理...")
                
                # 避免在后台线程中使用plt.close('all')，改用安全清理
                try:
                    import matplotlib.pyplot as plt
                    # 只清理当前图形，避免线程冲突
                    plt.close('all')
                except Exception as e:
                    self.log(f"图形清理失败: {e}")
                
                import gc
                
                # 只清理图形和垃圾回收，不删除模块缓存
                gc.collect()
                
                # 等待一小段时间确保清理完成
                time.sleep(1.0)  # 增加等待时间确保清理完成
                
                self.log("清理完成，开始执行第二次模拟...")
                
                # 第二次模拟（次要Levy指数）
                self.log("执行第二次模拟 (LEVY_EXP_SECONDARY)...")
                
                # 使用try-except包装模拟执行，防止崩溃
                try:
                    # 正确计算 max_life_seconds
                    if params["enable_lifespan_limit"]:
                        max_life_seconds = params["lifespan_years"] * 365 * 24 * 3600
                    else:
                        max_life_seconds = 0
                    
                    run_simulation_fast(
                        excel_path=params["map_path"],
                        n_agents=params["n_agents"],
                        max_steps=params["max_steps"],
                        direction_seed=params["direction_seed"],
                        levy_seed=params["levy_seed"],
                        temp_path=params["temp_path"],
                        levy_exp=LEVY_EXP_SECONDARY,
                        enable_lifespan_terminal=params["enable_lifespan_terminal"],
                        max_life_seconds=max_life_seconds,
                        direction_mode=params["direction_mode"],
                        show_interactive=False,
                        enable_global_simulation=params["enable_global_simulation"],
                        export_prefix=f"{params['export_prefix']}_2",
                        enable_b_supply=params["enable_b_supply"],
                        b_supply_percent=params["b_supply_percent"],
                        start_lat=params["start_lat"],
                        start_lon=params["start_lon"],
                        self_speed=params["self_speed"],
                        pure_survival_days=params["pure_survival_days"],
                        current_influence_mode=params["current_influence_mode"],
                        enable_lifespan_limit=params["enable_lifespan_limit"],
                        lifespan_years=params["lifespan_years"],
                        verbose_params=False  # 第二次模拟只打印关键差异信息
                    )
                except Exception as e:
                    self.log(f"第二次模拟执行失败: {e}")
                    # 尝试清理资源后继续
                    self._cleanup_after_simulation()
                    return False
                
                # 检查第二次模拟导出状态
                export_prefix_2 = f"{params['export_prefix']}_2"
                png_file_2 = f"{export_prefix_2}.png"
                excel_file_2 = f"{export_prefix_2}.xlsx"
                
                # 如果导出文件不存在，等待导出完成
                if not self.wait_for_export_completion(png_file_2, excel_file_2):
                    self.log("第二次模拟导出超时")
                
                # 第二次模拟完成后进行清理
                self.log("第二次模拟完成，执行资源清理...")
                self._cleanup_after_simulation()
                time.sleep(0.5)
                
                self.log("双Levy模式实验组执行完成，继续下一组实验...")
                
            else:
                # 单次模拟
                self.log("执行单次模拟...")
                
                # 使用try-except包装模拟执行，防止崩溃
                try:
                    # 正确计算 max_life_seconds
                    if params["enable_lifespan_limit"]:
                        max_life_seconds = params["lifespan_years"] * 365 * 24 * 3600
                    else:
                        max_life_seconds = 0
                    
                    run_simulation_fast(
                        excel_path=params["map_path"],
                        n_agents=params["n_agents"],
                        max_steps=params["max_steps"],
                        direction_seed=params["direction_seed"],
                        levy_seed=params["levy_seed"],
                        temp_path=params["temp_path"],
                        levy_exp=LEVY_EXP_PRIMARY,
                        enable_lifespan_terminal=params["enable_lifespan_terminal"],
                        max_life_seconds=max_life_seconds,
                        direction_mode=params["direction_mode"],
                        show_interactive=False,
                        enable_global_simulation=params["enable_global_simulation"],
                        export_prefix=params["export_prefix"],
                        enable_b_supply=params["enable_b_supply"],
                        b_supply_percent=params["b_supply_percent"],
                        start_lat=params["start_lat"],
                        start_lon=params["start_lon"],
                        self_speed=params["self_speed"],
                        pure_survival_days=params["pure_survival_days"],
                        current_influence_mode=params["current_influence_mode"],
                        enable_lifespan_limit=params["enable_lifespan_limit"],
                        lifespan_years=params["lifespan_years"],
                        verbose_params=True  # 单次模拟打印完整参数信息
                    )
                except Exception as e:
                    self.log(f"模拟执行失败: {e}")
                    # 尝试清理资源后继续
                    self._cleanup_after_simulation()
                    return False
                
                # 检查导出状态
                png_file = f"{params['export_prefix']}.png"
                excel_file = f"{params['export_prefix']}.xlsx"
                
                # 等待导出完成，确保PNG文件完全生成后再进行清理
                export_timeout = 120  # 增加等待时间到120秒
                if not self.wait_for_export_completion(png_file, excel_file, timeout=export_timeout):
                    self.log(f"模拟导出超时（超过{export_timeout}秒）")
                
                # 确保导出完成后，再进行资源清理
                self.log("等待导出完全完成...")
                time.sleep(2.0)  # 额外等待2秒确保导出完成
                
                # 单次模拟完成后进行清理
                self.log("单次模拟完成，执行资源清理...")
                self._cleanup_after_simulation()
                time.sleep(0.5)
            
            return True
            
        except Exception as e:
            self.log(f"执行模拟失败: {e}")
            return False
    
    def wait_for_export_completion(self, png_file, excel_file, timeout=300):
        """等待导出文件生成完成"""
        import time
        import os
        
        # 检查文件是否在result目录中（使用脚本所在目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        result_dir = os.path.join(script_dir, "result")
        png_file_in_result = os.path.join(result_dir, os.path.basename(png_file))
        excel_file_in_result = os.path.join(result_dir, os.path.basename(excel_file))
        
        self.log(f"检查导出文件: PNG={png_file}, Excel={excel_file}")
        self.log(f"Result目录文件: PNG={png_file_in_result}, Excel={excel_file_in_result}")
        
        # 详细检查文件状态
        png_exists = os.path.exists(png_file) or os.path.exists(png_file_in_result)
        excel_exists = os.path.exists(excel_file) or os.path.exists(excel_file_in_result)
        
        self.log(f"文件存在状态: PNG={png_exists}, Excel={excel_exists}")
        
        # 如果文件已经存在（在当前目录或result目录），说明导出已完成，直接返回成功
        if png_exists and excel_exists:
            self.log(f"导出文件已存在，无需等待: {png_file}, {excel_file}")
            return True
        
        self.log(f"等待文件生成，超时时间: {timeout}秒")
        
        # 等待文件生成
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # 检查文件是否存在
            png_exists = os.path.exists(png_file) or os.path.exists(png_file_in_result)
            excel_exists = os.path.exists(excel_file) or os.path.exists(excel_file_in_result)
            
            if png_exists and excel_exists:
                self.log(f"第{check_count}次检查: 导出文件生成完成: {png_file}, {excel_file}")
                return True
            
            # 显示检查进度
            if check_count % 10 == 0:  # 每10次检查显示一次进度
                elapsed = time.time() - start_time
                self.log(f"第{check_count}次检查: 已等待{elapsed:.1f}秒, PNG={png_exists}, Excel={excel_exists}")
            
            time.sleep(1)  # 每秒检查一次
        
        # 超时后再次检查最终状态
        png_exists = os.path.exists(png_file) or os.path.exists(png_file_in_result)
        excel_exists = os.path.exists(excel_file) or os.path.exists(excel_file_in_result)
        
        if png_exists and excel_exists:
            self.log(f"超时后最终检查: 导出文件生成完成: {png_file}, {excel_file}")
            return True
        
        self.log(f"导出文件等待超时: {png_file}, {excel_file} (PNG={png_exists}, Excel={excel_exists})")
        return False
    
    def log_event(self, experiment_index, export_prefix, event_type, message):
        """记录事件到事件日志文件"""
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with open(self.event_log_file, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp}|{experiment_index}|{export_prefix}|{event_type}|{message}\n")
        except Exception as e:
            print(f"记录事件失败: {e}")
    
    def _cleanup_after_simulation(self):
        """模拟执行后的资源清理（仅清理非GUI资源）"""
        try:
            import gc
            import sys
            
            # 注意：不在后台线程中清理Matplotlib资源，避免Tkinter线程冲突
            # plt.close('all') 会导致 RuntimeError: main thread is not in main loop
            
            # 清理NumPy数组缓存（释放CPU缓存）
            try:
                import numpy as np
                np.core._multiarray_umath._clear_floatstatus()
                self.log("NumPy缓存清理完成")
            except Exception as e:
                self.log(f"NumPy缓存清理失败: {e}")
            
            # 清理Python内部缓存
            try:
                # 清理函数缓存
                import functools
                functools._cache.clear()
                
                # 清理类型缓存
                if hasattr(sys, '_clear_type_cache'):
                    sys._clear_type_cache()
                
                # 清理框架缓存
                if hasattr(sys, '_clear_frame_cache'):
                    sys._clear_frame_cache()
                
                self.log("Python内部缓存清理完成")
            except Exception as e:
                self.log(f"Python内部缓存清理失败: {e}")
            
            # 强制垃圾回收（多轮）
            for i in range(3):
                collected = gc.collect()
                if collected > 0:
                    self.log(f"第{i+1}轮垃圾回收: 释放了{collected}个对象")
            
            # 清理模块级别的缓存
            self._cleanup_module_caches()
            
            self.log("资源清理完成（包括CPU缓存和垃圾回收）")
        except Exception as e:
            self.log(f"资源清理失败: {e}")
    
    def _cleanup_module_caches(self):
        """清理模块级别的缓存"""
        try:
            # 清理pandas缓存
            import pandas as pd
            if hasattr(pd, 'core') and hasattr(pd.core, 'algorithms'):
                pd.core.algorithms._factorize_cache.clear()
            
            # 清理可能的其他模块缓存
            import importlib
            for module_name in ['numpy', 'pandas', 'matplotlib']:
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, '_cache'):
                        module._cache.clear()
                except:
                    pass
            
            self.log("模块缓存清理完成")
        except Exception as e:
            self.log(f"模块缓存清理失败: {e}")


if __name__ == "__main__":
    # 测试核心逻辑模块
    core = AutomatedExperimentCore()
    core.automation_file_path = "C:/Users/cheng/Desktop/测试.xlsx"
    
    # 创建测试用的UI队列和进度更新函数
    test_queue = queue.Queue()
    
    def test_update_progress(progress, status):
        print(f"进度: {progress}%, 状态: {status}")
    
    try:
        core.execute_all_experiments(test_queue, test_update_progress)
    except Exception as e:
        print(f"测试失败: {e}")