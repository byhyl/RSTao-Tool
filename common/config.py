import os
from pathlib import Path

# 项目根目录（自动计算，永远正确）
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ====================== 软件基本信息 ======================
APP_NAME = "RSTao-Tool"
APP_VERSION = "1.0"
APP_AUTHOR = "RSTao"
APP_COPYRIGHT = "© 2026 RSTao 保留所有权利"

# ====================== 路径配置 ======================
ICON_PATH = BASE_DIR / "assets" / "icon.ico"
LOG_DIR = BASE_DIR / "logs"
TEMP_DIR = BASE_DIR / "temp"

# 自动创建目录
LOG_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ====================== 界面配置 ======================
WINDOW_SIZE = "1280x800"
DEFAULT_FONT = ("SimHei", 10)
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"

# ====================== 算法默认参数 ======================
# 特征检测
DEFAULT_HARRIS_K = 0.04
DEFAULT_HARRIS_THRESHOLD = 0.01
DEFAULT_WINDOW_SIZE = 3

# 影像匹配
DEFAULT_NCC_WINDOW = 11
DEFAULT_MATCH_THRESHOLD = 0.8
DEFAULT_NMS_RADIUS = 5

# ====================== 可视化配置 ======================
DEFAULT_FEATURE_COLOR = "red"
DEFAULT_MATCH_COLOR = "green"
DEFAULT_VECTOR_COLOR = (0.2, 0.5, 0.8)
SELECTED_COLOR = (1.0, 0.0, 0.0)
