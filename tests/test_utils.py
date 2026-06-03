"""工具函数测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from common.utils import non_max_suppression


class TestNMS:
    """非极大值抑制测试"""

    def test_empty_input(self):
        """空输入返回空列表"""
        assert non_max_suppression([], [], 0.5) == []

    def test_single_box(self):
        """单框不抑制"""
        boxes = [(0, 0, 10, 10)]
        scores = [0.9]
        keep = non_max_suppression(boxes, scores, 0.5)
        assert keep == [0]

    def test_non_overlapping_boxes(self):
        """不重叠的框全部保留"""
        boxes = [
            (0, 0, 10, 10),
            (100, 100, 110, 110),
            (200, 200, 210, 210),
        ]
        scores = [0.9, 0.8, 0.7]
        keep = non_max_suppression(boxes, scores, 0.5)
        assert len(keep) == 3

    def test_fully_overlapping_boxes(self):
        """完全重叠的框只保留最高分"""
        boxes = [
            (0, 0, 10, 10),
            (0, 0, 10, 10),
            (0, 0, 10, 10),
        ]
        scores = [0.7, 0.9, 0.5]
        keep = non_max_suppression(boxes, scores, 0.5)
        assert keep == [1]  # 最高分 index=1

    def test_partial_overlap_keep_highest(self):
        """部分重叠保留高分"""
        boxes = [
            (0, 0, 10, 10),
            (5, 5, 15, 15),   # 与第一个重叠
            (20, 20, 30, 30),  # 不重叠
        ]
        scores = [0.8, 0.9, 0.7]
        keep = non_max_suppression(boxes, scores, 0.5)
        assert 1 in keep  # 高分框保留
        assert 2 in keep  # 不重叠框保留

    def test_high_threshold_keeps_all(self):
        """高阈值保留更多框"""
        boxes = [
            (0, 0, 10, 10),
            (5, 5, 15, 15),
            (8, 8, 18, 18),
        ]
        scores = [0.9, 0.8, 0.7]
        keep = non_max_suppression(boxes, scores, 0.9)
        assert len(keep) == 3

    def test_low_threshold_keeps_one(self):
        """低阈值大量抑制"""
        boxes = [
            (0, 0, 10, 10),
            (5, 5, 15, 15),
        ]
        scores = [0.9, 0.8]
        keep = non_max_suppression(boxes, scores, 0.0)
        assert len(keep) == 1