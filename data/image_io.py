import cv2
import numpy as np
from common.logger import logger
from common.exceptions import FileReadError, FileWriteError

def read_image(file_path):
    """
    读取影像文件，统一返回RGB格式的numpy数组
    支持：jpg, png, bmp, tif 等所有常见格式
    """
    try:
        logger.info(f"读取影像: {file_path}")
        image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FileReadError(f"无法读取影像文件: {file_path}")
        # OpenCV默认BGR，转换为RGB
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    except Exception as e:
        logger.error(f"读取影像失败: {str(e)}", exc_info=True)
        raise FileReadError(f"读取影像失败: {str(e)}")

def save_image(image, file_path):
    """保存影像文件，自动处理中文路径"""
    try:
        logger.info(f"保存影像: {file_path}")
        # 转换为BGR格式
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        # 支持中文路径
        cv2.imencode('.jpg', image)[1].tofile(file_path)
        return True
    except Exception as e:
        logger.error(f"保存影像失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存影像失败: {str(e)}")