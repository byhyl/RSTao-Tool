"""批量处理引擎 — 支持批量特征检测、批量影像匹配"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from common.logger import logger
from common import utils


@dataclass
class BatchTask:
    """单个批处理任务"""
    input_path: str
    output_dir: str
    params: Dict = field(default_factory=dict)
    status: str = "pending"  # pending / running / done / failed
    result: Optional[str] = None
    error: str = ""
    duration: float = 0.0


@dataclass
class BatchResult:
    """批处理结果汇总"""
    total: int = 0
    success: int = 0
    failed: int = 0
    tasks: List[BatchTask] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed(self) -> float:
        return self.end_time - self.start_time

    @property
    def success_rate(self) -> float:
        return self.success / self.total * 100 if self.total > 0 else 0.0


class BatchProcessor:
    """批量处理引擎"""

    SUPPORTED_FORMATS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None

    def on_progress(self, callback: Callable[[int, int, str], None]):
        """设置进度回调"""
        self._progress_callback = callback

    def _report_progress(self, current: int, total: int, message: str = ""):
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def collect_images(self, input_dir: str, recursive: bool = False) -> List[str]:
        """收集目录下所有支持的影像文件"""
        images = []
        base = Path(input_dir)
        if not base.exists():
            return images

        pattern = "**/*" if recursive else "*"
        for ext in self.SUPPORTED_FORMATS:
            for p in base.glob(pattern):
                if p.suffix.lower() == ext:
                    images.append(str(p))
        return sorted(images)  # 可限制数量

    def batch_feature_detect(
        self,
        input_dir: str,
        output_dir: str,
        harris_k: float = 0.04,
        threshold: float = 0.01,
        recursive: bool = False,
    ) -> BatchResult:
        """批量特征检测"""
        images = self.collect_images(input_dir, recursive)
        if not images:
            logger.warning("未找到支持的影像文件")
            return BatchResult()

        result = BatchResult(total=len(images), start_time=time.time())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        def process_one(img_path: str) -> BatchTask:
            task = BatchTask(input_path=img_path, output_dir=output_dir,
                           params={"harris_k": harris_k, "threshold": threshold})
            try:
                task.status = "running"
                gray = utils.imread_chinese(img_path, cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    raise ValueError(f"无法读取影像: {img_path}")

                gray_f = np.float32(gray)
                dst = cv2.cornerHarris(gray_f, 2, 3, harris_k)
                dst = cv2.dilate(dst, None)
                keypoints = np.argwhere(dst > threshold * dst.max())

                # 保存结果
                name = Path(img_path).stem
                out_path = os.path.join(output_dir, f"{name}_features.csv")
                np.savetxt(out_path, keypoints, fmt="%d", delimiter=",",
                          header="y,x", comments="")
                task.result = out_path
                task.status = "done"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.error(f"批量特征检测失败 [{img_path}]: {e}")
            return task

        return self._execute_batch(images, process_one, result)

    def batch_match(
        self,
        template_path: str,
        input_dir: str,
        output_dir: str,
        method: int = cv2.TM_CCOEFF_NORMED,
        threshold: float = 0.8,
        recursive: bool = False,
    ) -> BatchResult:
        """批量影像匹配（模板匹配）"""
        template = utils.imread_chinese(template_path)
        if template is None:
            raise ValueError(f"模板影像读取失败: {template_path}")

        images = self.collect_images(input_dir, recursive)
        if not images:
            return BatchResult()

        result = BatchResult(total=len(images), start_time=time.time())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        def process_one(img_path: str) -> BatchTask:
            task = BatchTask(input_path=img_path, output_dir=output_dir,
                           params={"method": method, "threshold": threshold})
            try:
                task.status = "running"
                img = utils.imread_chinese(img_path)
                if img is None:
                    raise ValueError(f"无法读取影像: {img_path}")

                res = cv2.matchTemplate(img, template, method)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                    top_left = min_loc
                    score = 1.0 - min_val
                else:
                    top_left = max_loc
                    score = max_val

                task.params["score"] = float(score)

                if score >= threshold:
                    h, w = template.shape[:2]
                    bottom_right = (top_left[0] + w, top_left[1] + h)
                    result_img = img.copy()
                    cv2.rectangle(result_img, top_left, bottom_right, (0, 255, 0), 2)

                    name = Path(img_path).stem
                    out_path = os.path.join(output_dir, f"{name}_matched.png")
                    utils.imwrite_chinese(out_path, result_img)
                    task.result = out_path
                    task.status = "done"
                else:
                    task.status = "done"
                    task.result = "below_threshold"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
            return task

        return self._execute_batch(images, process_one, result, "batch_match")

    def _execute_batch(
        self, images: List[str], worker: Callable[[str], BatchTask],
        result: BatchResult, task_type: str = "batch"
    ) -> BatchResult:
        """执行批量任务"""
        total = len(images)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(worker, p): i for i, p in enumerate(images)}
            for future in as_completed(futures):
                task = future.result()
                result.tasks.append(task)
                if task.status == "done":
                    result.success += 1
                else:
                    result.failed += 1
                self._report_progress(
                    result.success + result.failed, total,
                    f"{task_type}: {Path(task.input_path).name}"
                )

        result.end_time = time.time()
        logger.info(
            f"批量处理完成: {total} 个任务, 成功 {result.success}, "
            f"失败 {result.failed}, 耗时 {result.elapsed:.1f}s"
        )
        return result
