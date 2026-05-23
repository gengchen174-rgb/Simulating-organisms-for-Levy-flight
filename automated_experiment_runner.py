"""
自动化实验执行器 - 主脚本
整合UI模块和核心逻辑模块
"""

from automated_experiment_ui import AutomatedExperimentUI
from automated_experiment_core import AutomatedExperimentCore


def main():
    """主函数"""
    # 创建核心逻辑模块实例
    core = AutomatedExperimentCore()
    
    # 创建UI模块实例
    ui = AutomatedExperimentUI(core)
    
    # 运行UI
    ui.run()


if __name__ == "__main__":
    main()