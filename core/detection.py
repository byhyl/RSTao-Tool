"""深度学习目标检测 — ONNX Runtime 推理"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from common.logger import logger


@dataclass
class DetectionResult:
    """检测结果"""

    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    score: float
    class_id: int
    class_name: str = ""


@dataclass
class DetectionOutput:
    """单次检测输出"""

    results: List[DetectionResult] = field(default_factory=list)
    inference_time_ms: float = 0.0
    image_size: Tuple[int, int] = (0, 0)

    @property
    def count(self) -> int:
        return len(self.results)

    @property
    def has_detections(self) -> bool:
        return len(self.results) > 0


class ONNXDetector:
    """ONNX Runtime 目标检测器

    支持模型: YOLOv5/v8/v11, 以及其他 ONNX 格式目标检测模型
    """

    def __init__(self, model_path: str = "", confidence: float = 0.5, iou_threshold: float = 0.45):
        self.model_path = model_path
        self.confidence = confidence
        self.iou_threshold = iou_threshold
        self._session = None
        self._input_name = ""
        self._input_shape = (640, 640)
        self._names: dict = {}
        self._available = False

        if model_path and os.path.exists(model_path):
            self.load_model(model_path)

    @property
    def available(self) -> bool:
        return self._available

    def load_model(self, model_path: str) -> bool:
        """加载 ONNX 模型"""
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            input_shape = self._session.get_inputs()[0].shape
            # Handle dynamic shapes (e.g., -1 for batch or dimensions)
            h_idx, w_idx = (2, 3) if len(input_shape) == 4 else (1, 2)
            h = (
                input_shape[h_idx]
                if isinstance(input_shape[h_idx], int) and input_shape[h_idx] > 0
                else 640
            )
            w = (
                input_shape[w_idx]
                if isinstance(input_shape[w_idx], int) and input_shape[w_idx] > 0
                else 640
            )
            self._input_shape = (w, h)
            self.model_path = model_path
            self._available = True
            logger.info(f"ONNX 模型加载成功: {model_path} ({self._input_shape})")
            return True
        except ImportError:
            logger.error("onnxruntime 未安装，请执行: pip install onnxruntime")
        except Exception as e:
            logger.error(f"加载 ONNX 模型失败: {e}")
        return False

    def set_classes(self, names: dict):
        """设置类别名称映射"""
        self._names = names

    def detect(self, image: np.ndarray) -> DetectionOutput:
        """执行目标检测"""
        if not self._available:
            return DetectionOutput()

        import time

        t0 = time.time()

        h, w = image.shape[:2]
        # 预处理: resize + normalize
        input_tensor = self._preprocess(image)
        # 推理
        outputs = self._session.run(None, {self._input_name: input_tensor})
        # 后处理: NMS
        results = self._postprocess(outputs, (w, h))

        elapsed = (time.time() - t0) * 1000
        return DetectionOutput(results=results, inference_time_ms=elapsed, image_size=(w, h))

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """YOLO 标准预处理"""
        img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, self._input_shape)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        return img

    def _postprocess(self, outputs, original_size: Tuple[int, int]) -> List[DetectionResult]:
        """YOLO 后处理: 解析输出 + NMS"""
        results = []
        predictions = np.asarray(outputs[0])  # YOLOv5: (1, N, 85), YOLOv8/v11: (1, 84, N)

        if len(predictions.shape) == 3:
            predictions = predictions[0]  # (N, dims)
        if len(predictions.shape) == 2:
            rows, cols = predictions.shape
            name_count = len(self._names)
            channel_first = (
                (name_count > 0 and rows in (name_count + 4, name_count + 5))
                or rows in (84, 85)
                or (rows >= 20 and cols > rows)
            )
            if channel_first:
                predictions = predictions.T

        ow, oh = original_size
        iw, ih = self._input_shape
        scale_x = ow / iw
        scale_y = oh / ih

        for pred in predictions:
            if len(pred) < 6:
                continue

            if len(pred) == 6:
                x1, y1, x2, y2 = pred[:4]
                score = float(pred[4])
                class_id = int(pred[5])
                if x2 <= x1 or y2 <= y1:
                    cx, cy, bw, bh = pred[:4]
                    x1, y1 = cx - bw / 2, cy - bh / 2
                    x2, y2 = cx + bw / 2, cy + bh / 2
            else:
                name_count = len(self._names)
                has_objectness = (
                    (name_count > 0 and len(pred) == name_count + 5)
                    or len(pred) == 85
                    or (len(pred) != 84 and float(pred[4]) > float(np.max(pred[5:])))
                )
                if has_objectness:
                    objectness = float(pred[4])
                    class_scores = pred[5:]
                    class_id = int(np.argmax(class_scores))
                    score = objectness * float(class_scores[class_id])
                else:
                    class_scores = pred[4:]
                    class_id = int(np.argmax(class_scores))
                    score = float(class_scores[class_id])

                # 解析边界框 (中心点格式 -> 左上/右下)
                cx, cy, bw, bh = pred[:4]
                x1 = (cx - bw / 2) * scale_x
                y1 = (cy - bh / 2) * scale_y
                x2 = (cx + bw / 2) * scale_x
                y2 = (cy + bh / 2) * scale_y

            if score < self.confidence:
                continue

            x1 = int(x1)
            y1 = int(y1)
            x2 = int(x2)
            y2 = int(y2)

            # 裁剪到图像范围内
            x1 = max(0, min(x1, ow))
            y1 = max(0, min(y1, oh))
            x2 = max(0, min(x2, ow))
            y2 = max(0, min(y2, oh))

            class_name = self._names.get(class_id, str(class_id))
            results.append(
                DetectionResult(
                    bbox=(x1, y1, x2, y2), score=score, class_id=class_id, class_name=class_name
                )
            )

        # NMS
        results = self._nms(results)
        return results

    def _nms(self, detections: List[DetectionResult]) -> List[DetectionResult]:
        """非极大值抑制"""
        if not detections:
            return []

        boxes = np.array([d.bbox for d in detections])
        scores = np.array([d.score for d in detections])

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            iou = (w * h) / (areas[order[1:]] + areas[i] - w * h + 1e-10)

            inds = np.where(iou <= self.iou_threshold)[0]
            order = order[inds + 1]

        return [detections[i] for i in keep]

    def draw_detections(
        self, image: np.ndarray, output: DetectionOutput, color: tuple = (0, 255, 100)
    ) -> np.ndarray:
        """在图像上绘制检测结果"""
        vis = image.copy()
        for det in output.results:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {det.score:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(vis, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        return vis
