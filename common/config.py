import os
from pathlib import Path

from common.app_icon import resolve_app_icon_path
from common.paths import get_logs_dir, get_temp_dir
from common.version import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_VERSION

# 项目根目录（自动计算，永远正确）
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ====================== 软件基本信息 ======================
# ====================== 路径配置 ======================
ICON_PATH = resolve_app_icon_path()
LOG_DIR = get_logs_dir()
TEMP_DIR = get_temp_dir()

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
