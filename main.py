import hashlib
import json
import uuid
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict

import customtkinter as ctk
import wmi
from tkinter import messagebox

# 本地模块导入
from ui import MainWindow
from common.crypto import aes_gcm_encrypt, aes_gcm_decrypt, generate_machine_code_hash
from common.logger import logger

# ====================== 配置常量 ======================
@dataclass
class AuthConfig:
    LICENSE_FILE_NAME: str = ".license.dat"
    ACTIVATION_WINDOW_SIZE: str = "500x420"
    ACTIVATION_WINDOW_TITLE: str = "RSTao-Tool - 授权激活"
    FONT_MAIN: tuple = ("Microsoft YaHei", 14)
    FONT_SMALL: tuple = ("Microsoft YaHei", 12)
    BTN_ACTIVE_COLOR: str = "#2563eb"
    # 在线激活服务器地址（可配置）
    ACTIVATION_SERVER_URL: str = "http://127.0.0.1:18080"
    ACTIVATION_TIMEOUT: int = 10  # 秒

