import os
import threading

import cv2
import matplotlib.pyplot as plt
import numpy as np

from .config import DEFAULT_FONT
from .exceptions import AppBaseException
from .logger import logger


# common/utils.py
def set_chinese_font():
    """统一设置Matplotlib中文显示"""
    # Windows系统优先使用微软雅黑和黑体
    plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


def safe_execute(func):
    """安全执行装饰器，捕获所有异常并统一处理"""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AppBaseException as e:
            logger.error(f"业务异常: {e.message}", exc_info=True)
            from tkinter import messagebox

            messagebox.showerror("错误", e.message)
            return None
        except Exception as e:
            logger.critical(f"未捕获的异常: {str(e)}", exc_info=True)
            from tkinter import messagebox

            messagebox.showerror("系统错误", f"发生未知错误：{str(e)}\n请查看日志文件获取详细信息")
            return None

    return wrapper


def run_in_background(func):
    """后台执行装饰器，不阻塞UI"""

    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()

    return wrapper


def normalize_image(image):
    """将影像归一化到0-255"""
    if image.dtype != np.uint8:
        image = ((image - image.min()) / (image.max() - image.min()) * 255).astype(np.uint8)
    return image


# 在common/utils.py末尾添加
def put_chinese_text(img, text, position, font_size, color):
    """在图像上绘制中文文字"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    try:
        font = ImageFont.truetype("simhei.ttf", font_size)
    except Exception as e:
        logger.debug(f'字体加载降级: {e}'); font = ImageFont.load_default()

    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def non_max_suppression(boxes, scores, iou_threshold):
    """非极大值抑制"""
    if len(boxes) == 0:
        return []

    boxes = np.array(boxes)
    scores = np.array(scores)

    # 按得分降序排序
    indices = np.argsort(scores)[::-1]
    keep = []

    while len(indices) > 0:
        # 取得分最高的框
        current = indices[0]
        keep.append(current)

        if len(indices) == 1:
            break

        # 计算IOU
        x1 = np.maximum(boxes[current, 0], boxes[indices[1:], 0])
        y1 = np.maximum(boxes[current, 1], boxes[indices[1:], 1])
        x2 = np.minimum(boxes[current, 2], boxes[indices[1:], 2])
        y2 = np.minimum(boxes[current, 3], boxes[indices[1:], 3])

        intersection = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        area_current = (boxes[current, 2] - boxes[current, 0]) * (
            boxes[current, 3] - boxes[current, 1]
        )
        area_others = (boxes[indices[1:], 2] - boxes[indices[1:], 0]) * (
            boxes[indices[1:], 3] - boxes[indices[1:], 1]
        )

        iou = intersection / (area_current + area_others - intersection)

        # 保留IOU小于阈值的框
        indices = indices[1:][iou < iou_threshold]

    return keep


def imread_chinese(path, flags=cv2.IMREAD_COLOR):
    """支持中文路径的cv2.imread替代函数"""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
        img = cv2.imdecode(data, flags)
        if img is None:
            raise ValueError(f'无法读取图像: {path}')
        return img
    except Exception as e:
        logger.error(f'读取图像失败 [{path}]: {e}')
        raise

def imwrite_chinese(path, img, params=None):
    """支持中文路径的cv2.imwrite替代函数"""
    try:
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            ext = '.png'
        _, buf = cv2.imencode(ext, img, params or [])
        with open(path, 'wb') as f:
            f.write(buf)
        return True
    except Exception as e:
        logger.error(f'写入图像失败 [{path}]: {e}')
        return False
