"""目标检测后处理测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from core.detection import ONNXDetector


def test_yolov5_objectness_multiplies_class_score():
    detector = ONNXDetector(confidence=0.5)
    detector._input_shape = (100, 100)
    detector.set_classes({0: "A", 1: "B"})

    output = [np.array([[[50, 50, 20, 20, 0.9, 0.1, 0.8]]], dtype=np.float32)]
    results = detector._postprocess(output, (100, 100))

    assert len(results) == 1
    assert results[0].class_id == 1
    assert results[0].class_name == "B"
    assert abs(results[0].score - 0.72) < 1e-6


def test_yolov8_channel_first_output_is_transposed():
    detector = ONNXDetector(confidence=0.5)
    detector._input_shape = (100, 100)
    detector.set_classes({0: "A", 1: "B"})

    output = [np.zeros((1, 6, 2), dtype=np.float32)]
    output[0][0, :, 0] = [50, 50, 20, 20, 0.1, 0.8]
    output[0][0, :, 1] = [30, 30, 10, 10, 0.7, 0.2]

    results = detector._postprocess(output, (100, 100))

    assert len(results) == 1
    assert results[0].class_id == 0
    assert results[0].class_name == "A"
    assert results[0].bbox == (25, 25, 35, 35)


def test_six_column_boxes_scale_to_original_size():
    detector = ONNXDetector(confidence=0.5)
    detector._input_shape = (640, 640)

    output = [np.array([[[100, 100, 200, 200, 0.9, 1]]], dtype=np.float32)]
    results = detector._postprocess(output, (1280, 1280))

    assert len(results) == 1
    assert results[0].bbox == (200, 200, 400, 400)
