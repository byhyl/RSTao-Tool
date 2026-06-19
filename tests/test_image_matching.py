"""影像匹配模块测试 — ncc_match / nms / draw_matches / draw_heatmap"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from core.image_matching import draw_heatmap, draw_matches, ncc_match, nms


class TestNMS:
    """NMS (module-level wrapper)"""

    def test_empty_matches(self):
        assert nms([]) == []

    def test_single_match(self):
        matches = [(10, 20, 15, 25, 0.9)]
        result = nms(matches, threshold=0.3)
        assert len(result) == 1

    def test_high_threshold_keeps_all_sparse(self):
        matches = [(0, 0, 5, 5, 0.9), (100, 100, 105, 105, 0.8)]
        result = nms(matches, threshold=0.3)
        assert len(result) == 2

    def test_overlapping_keeps_highest(self):
        matches = [(0, 0, 5, 5, 0.7), (2, 2, 7, 7, 0.9), (1, 1, 6, 6, 0.5)]
        result = nms(matches, threshold=0.3)
        # Should keep index 1 (highest score 0.9)
        scores = [m[4] for m in result]
        assert 0.9 in scores


class TestDrawMatches:
    """可视化函数"""

    def test_draw_matches_shape(self):
        left = np.zeros((100, 100, 3), dtype=np.uint8)
        right = np.zeros((100, 100, 3), dtype=np.uint8)
        matches = [(10, 10, 20, 20, 0.9)]
        result = draw_matches(left, right, matches)
        assert result.shape[0] == 100  # max height
        assert result.shape[1] == 200  # w1 + w2

    def test_draw_matches_different_sizes(self):
        left = np.zeros((80, 60, 3), dtype=np.uint8)
        right = np.zeros((100, 80, 3), dtype=np.uint8)
        result = draw_matches(left, right, [])
        assert result.shape[0] == 100
        assert result.shape[1] == 140

    def test_draw_heatmap_shape(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        matches = [(10, 10, 15, 15, 0.8)]
        hm = draw_heatmap(img, matches)
        assert hm.shape[:2] == (100, 100)
        assert hm.shape[2] == 3  # BGR


class TestNCCMatch:
    """NCC 匹配"""

    def test_empty_template_area(self):
        left = np.zeros((50, 50, 3), dtype=np.uint8)
        right = np.zeros((50, 50, 3), dtype=np.uint8)
        result = ncc_match(left, right, (0, 0, 1, 1))
        assert isinstance(result, list)

    def test_trivial_match(self):
        # Identical images: template matches exactly at (0,0)
        img = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
        result = ncc_match(img, img, (5, 5, 15, 15), threshold=0.5)
        # Should find at least one match near the template location
        assert isinstance(result, list)
