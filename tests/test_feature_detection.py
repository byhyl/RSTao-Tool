"""特征检测算法测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from core.feature_detection import FeatureDetection


@pytest.fixture
def detector():
    return FeatureDetection()


@pytest.fixture
def sample_gray_image():
    """创建模拟灰度图（白底黑色方块）"""
    img = np.ones((100, 100), dtype=np.uint8) * 255
    img[40:60, 40:60] = 0  # 黑色方块
    return img


@pytest.fixture
def sample_color_image():
    """创建模拟彩色图"""
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    img[40:60, 40:60] = [0, 0, 0]
    return img


class TestFeatureDetection:
    """特征检测测试"""

    def test_harris_detect_returns_mask_and_count(self, detector, sample_gray_image):
        """Harris 检测返回 mask 和点数"""
        mask, count = detector.harris_detect(sample_gray_image, harris_k=0.04, threshold=0.01)
        assert isinstance(mask, np.ndarray)
        assert mask.shape == sample_gray_image.shape
        assert isinstance(count, int)
        assert count >= 0

    def test_moravec_detect(self, detector, sample_gray_image):
        """Moravec 检测"""
        mask, count = detector.moravec_detect(sample_gray_image, threshold=0.05)
        assert mask.shape == sample_gray_image.shape
        assert count >= 0

    def test_forstner_detect(self, detector, sample_gray_image):
        """Forstner 检测"""
        mask, count = detector.forstner_detect(sample_gray_image, threshold=0.001)
        assert mask.shape == sample_gray_image.shape
        assert count >= 0

    def test_susan_detect(self, detector, sample_gray_image):
        """SUSAN 检测"""
        mask, count = detector.susan_detect(sample_gray_image, susan_t=25, threshold=0.2)
        assert mask.shape == sample_gray_image.shape
        assert count >= 0

    def test_detection_on_blank_image(self, detector):
        """空白图像检测角点数为0"""
        blank = np.ones((100, 100), dtype=np.uint8) * 128
        _, count = detector.harris_detect(blank, harris_k=0.04, threshold=0.01)
        assert count == 0

    def test_detection_on_corner_image(self, detector):
        """明显角点图像应有角点"""
        # 四角有黑白对比的图
        img = np.ones((100, 100), dtype=np.uint8) * 128
        img[0:50, 0:50] = 0
        img[50:100, 50:100] = 0
        _, count = detector.harris_detect(img, harris_k=0.04, threshold=0.005)
        assert count > 0

    def test_load_image_none_path(self, detector):
        """空路径返回 None"""
        assert detector.load_image("") is None

    def test_rotate_image(self, detector, sample_color_image):
        """旋转不改变尺寸"""
        rotated = detector.rotate_image(sample_color_image, angle=45)
        assert rotated.shape == sample_color_image.shape

    def test_rotate_image_90(self, detector, sample_color_image):
        """90度旋转"""
        rotated = detector.rotate_image(sample_color_image, angle=90)
        assert rotated is not None
        assert rotated.shape == sample_color_image.shape
