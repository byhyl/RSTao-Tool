import logging
from logging.handlers import RotatingFileHandler
from .config import LOG_DIR, APP_NAME

def setup_logger():
    """配置全局日志系统"""
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 清除已有处理器
    if logger.handlers:
        logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出（按大小滚动，最多保留5个日志文件，每个10MB）
    log_file = LOG_DIR / f"{APP_NAME}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# 全局日志实例
logger = setup_logger()