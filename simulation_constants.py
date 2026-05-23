# ---- 常量定义 ---------------------------------------------------
MIN_LON, MAX_LON = -180, 180.0
MIN_LAT, MAX_LAT = -90, 90
M_PER_DEG_LAT = 111319.9
# 生物移动速度（仅用于DEFAULT_CONFIG初始化）
SELF_SPEED = 3  # 仅用于DEFAULT_CONFIG初始化
CURRENT_SPEED = 0.1
LEVY_SCALE = 1000.0
# ------------ 两个固定LEVY_EXP值（用户可直接修改这里）------------
LEVY_EXP_PRIMARY = 1.5   # 第一个指数（原默认值）
LEVY_EXP_SECONDARY = 2  # 第二个指数（用户可自定义）
# -------------------------------------------------------------------
# 初始默认投射地点（这些值现在在DEFAULT_CONFIG中定义）
start_lat, start_lon = 20, 100  # 仅用于DEFAULT_CONFIG初始化
DEFAULT_AGENTS = 200  # 仅用于DEFAULT_CONFIG初始化
DEFAULT_STEPS = 100000  # 仅用于DEFAULT_CONFIG初始化

# ==================== 寿命控制 ====================
ENABLE_LIFESPAN_LIMIT = False  # 默认寿命上限功能
LIFESPAN_YEARS = 30    # 默认寿命上限（年），仅在启用时有效

TEMP_SCORE = [
    (5, 10, 0.814983),
    (10, 15, 1.470517),
    (15, 20, 2.600124),
    (20, 25, 4.509877),
    (25, 30, 7.679751),
    (30, 35, 12.194591),
    (35, 40, 4.353828),
]
# ---- 全局模式参数 & 禁用方向设置 -------------------------------
direction_mode = "weighted"  # "weighted" (默认) 或 "random"
disabled_directions = {"N": False, "S": False, "E": False, "W": False}
# 洋流影响模式： "with_current"（默认） 或 "no_current"
current_influence_mode = "with_current"

# 新增：配置文件默认值（包含所有需要记忆的参数）
DEFAULT_CONFIG = {
    "number_of_agents": DEFAULT_AGENTS,
    "max_steps": DEFAULT_STEPS,
    "enable_lifespan_limit": ENABLE_LIFESPAN_LIMIT,
    "lifespan_years": LIFESPAN_YEARS,
    "current_influence_mode": "with_current",  # 直接写默认值，避免依赖全局变量
    "start_lat": start_lat,
    "start_lon": start_lon,
    "self_speed": SELF_SPEED,
    "pure_full_state_survival_days": 10,
    "direction_seed": None,  # 原随机种子重命名为"方向种子"，更清晰
    "levy_seed": None,        # 新增：Levy步长种子
    "enable_lifespan_terminal": False,  # 新增：是否以Agent累计寿命为结束条件
    "direction_mode": "weighted",  # 新增：方向模式选择
    "enable_b_supply": False,  # 新增：是否启用B区域补给功能
    "b_supply_percent": 50,    # 新增：B区域补给百分比（相对于G区域补给时间）
    "enable_dual_levy": False,  # 新增：是否启用双LEVY_EXP模式
    "maximize_window": False,  # 新增：模拟结束后是否最大化窗口
    "auto_save_visualization": False,  # 新增：是否在模拟过程中自动保存可视化
    "record_video": False  # 新增：是否录制模拟视频
}
# ---- 全局模拟设置 -------------------------------
ENABLE_GLOBAL_SIMULATION = True  # 默认开启全球模拟
