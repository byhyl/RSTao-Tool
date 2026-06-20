"""批量处理引擎 — 支持批量特征检测、批量影像匹配"""

import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from common import utils
from common.logger import logger
from .image_processing import ImageProcessingCore
from data.image_io import read_raster_data, save_raster_result


@dataclass
class BatchTask:
    """单个批处理任务"""

    input_path: str
    output_dir: str
    params: Dict = field(default_factory=dict)
    status: str = "pending"  # pending / running / done / skipped / failed
    result: Optional[str] = None
    error: str = ""
    duration: float = 0.0


@dataclass
class BatchResult:
    """批处理结果汇总"""

    total: int = 0
    success: int = 0
    skipped: int = 0
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

    @property
    def failed_tasks(self) -> List[BatchTask]:
        return [task for task in self.tasks if task.status == "failed"]


class BatchProcessor:
    """批量处理引擎"""

    SUPPORTED_FORMATS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None
        self._task_callback: Optional[Callable[[BatchTask, int, int], None]] = None

    def on_progress(self, callback: Callable[[int, int, str], None]):
        """设置进度回调"""
        self._progress_callback = callback

    def on_task_update(self, callback: Callable[[BatchTask, int, int], None]):
        """Set a callback invoked when a task finishes."""
        self._task_callback = callback

    def _report_progress(self, current: int, total: int, message: str = ""):
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def _report_task(self, task: BatchTask, current: int, total: int):
        if self._task_callback:
            self._task_callback(task, current, total)

    def iter_images(self, input_dir, recursive=False):
        """Generator: yield supported image files one by one"""
        base = Path(input_dir)
        if not base.exists():
            return
        pattern = "**/*" if recursive else "*"
        for p in base.glob(pattern):
            if p.is_file() and p.suffix.lower() in self.SUPPORTED_FORMATS:
                yield str(p)

    def collect_images(self, input_dir, recursive=False, limit=0):
        """Collect supported images (with optional limit)"""
        images = []
        for path in self.iter_images(input_dir, recursive):
            images.append(path)
            if limit > 0 and len(images) >= limit:
                break
        return sorted(images)

    def batch_feature_detect(
        self,
        input_dir: str,
        output_dir: str,
        harris_k: float = 0.04,
        threshold: float = 0.01,
        recursive: bool = False,
        skip_existing: bool = False,
    ) -> BatchResult:
        """批量特征检测"""
        images = self.collect_images(input_dir, recursive)
        if not images:
            logger.warning("未找到支持的影像文件")
            return BatchResult()

        return self.batch_feature_detect_paths(
            images,
            output_dir,
            harris_k=harris_k,
            threshold=threshold,
            skip_existing=skip_existing,
        )

    def batch_feature_detect_paths(
        self,
        image_paths: List[str],
        output_dir: str,
        harris_k: float = 0.04,
        threshold: float = 0.01,
        skip_existing: bool = False,
    ) -> BatchResult:
        """Run feature detection for an explicit image path list."""
        images = sorted(image_paths)
        if not images:
            return BatchResult()

        result = BatchResult(total=len(images), start_time=time.time())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        def process_one(img_path: str) -> BatchTask:
            task = BatchTask(
                input_path=img_path,
                output_dir=output_dir,
                params={"harris_k": harris_k, "threshold": threshold},
            )
            started = time.time()
            try:
                task.status = "running"
                name = Path(img_path).stem
                out_path = os.path.join(output_dir, f"{name}_features.csv")
                if skip_existing and os.path.exists(out_path):
                    task.result = out_path
                    task.status = "skipped"
                    return task

                gray = utils.imread_chinese(img_path, cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    raise ValueError(f"无法读取影像: {img_path}")

                gray_f = np.float32(gray)
                dst = cv2.cornerHarris(gray_f, 2, 3, harris_k)
                dst = cv2.dilate(dst, None)
                keypoints = np.argwhere(dst > threshold * dst.max())

                # 保存结果
                np.savetxt(out_path, keypoints, fmt="%d", delimiter=",", header="y,x", comments="")
                task.result = out_path
                task.status = "done"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.error(f"批量特征检测失败 [{img_path}]: {e}")
            finally:
                task.duration = time.time() - started
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
        skip_existing: bool = False,
    ) -> BatchResult:
        """批量影像匹配（模板匹配）"""
        images = self.collect_images(input_dir, recursive)
        if not images:
            return BatchResult()

        return self.batch_match_paths(
            template_path,
            images,
            output_dir,
            method=method,
            threshold=threshold,
            skip_existing=skip_existing,
        )

    def batch_match_paths(
        self,
        template_path: str,
        image_paths: List[str],
        output_dir: str,
        method: int = cv2.TM_CCOEFF_NORMED,
        threshold: float = 0.8,
        skip_existing: bool = False,
    ) -> BatchResult:
        """Run image matching for an explicit image path list."""
        template = utils.imread_chinese(template_path)
        if template is None:
            raise ValueError(f"模板影像读取失败: {template_path}")

        images = sorted(image_paths)
        if not images:
            return BatchResult()

        result = BatchResult(total=len(images), start_time=time.time())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        def process_one(img_path: str) -> BatchTask:
            task = BatchTask(
                input_path=img_path,
                output_dir=output_dir,
                params={"method": method, "threshold": threshold},
            )
            started = time.time()
            try:
                task.status = "running"
                name = Path(img_path).stem
                out_path = os.path.join(output_dir, f"{name}_matched.png")
                if skip_existing and os.path.exists(out_path):
                    task.result = out_path
                    task.status = "skipped"
                    return task

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

                    utils.imwrite_chinese(out_path, result_img)
                    task.result = out_path
                    task.status = "done"
                else:
                    task.status = "done"
                    task.result = "below_threshold"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
            finally:
                task.duration = time.time() - started
            return task

        return self._execute_batch(images, process_one, result, "batch_match")

    def batch_image_process(
        self,
        input_dir: str,
        output_dir: str,
        operator_id: str,
        params: Optional[Dict] = None,
        recursive: bool = False,
        skip_existing: bool = False,
        output_ext: str = ".png",
    ) -> BatchResult:
        """Run a registered image processing operator for an input directory."""
        images = self.collect_images(input_dir, recursive)
        if not images:
            return BatchResult()
        return self.batch_image_process_paths(
            images,
            output_dir,
            operator_id,
            params=params,
            skip_existing=skip_existing,
            output_ext=output_ext,
        )

    def batch_image_process_paths(
        self,
        image_paths: List[str],
        output_dir: str,
        operator_id: str,
        params: Optional[Dict] = None,
        skip_existing: bool = False,
        output_ext: str = ".png",
    ) -> BatchResult:
        """Run a registered image processing operator for explicit image paths."""
        images = sorted(image_paths)
        if not images:
            return BatchResult()

        core = ImageProcessingCore()
        spec = core.get_operator(operator_id)
        base_params = dict(params or {})
        reference_path = base_params.pop("reference_path", "")
        if reference_path and operator_id == "hist_match_reference":
            base_params["reference_image"] = read_raster_data(reference_path, preserve_dtype=True)

        clean_ext = output_ext if str(output_ext).startswith(".") else f".{output_ext}"
        clean_ext = clean_ext.lower()
        if clean_ext not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
            clean_ext = ".png"

        result = BatchResult(total=len(images), start_time=time.time())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        def process_one(img_path: str) -> BatchTask:
            task = BatchTask(
                input_path=img_path,
                output_dir=output_dir,
                params={
                    "operator_id": operator_id,
                    "operator": spec.name,
                    **{k: v for k, v in base_params.items() if k != "reference_image"},
                },
            )
            started = time.time()
            try:
                task.status = "running"
                source_ext = Path(img_path).suffix.lower()
                ext = clean_ext
                if clean_ext in {".tif", ".tiff"} and source_ext not in {
                    ".tif",
                    ".tiff",
                    ".img",
                    ".jp2",
                    ".vrt",
                }:
                    ext = ".png"
                name = Path(img_path).stem
                out_path = os.path.join(output_dir, f"{name}_{operator_id}{ext}")
                if skip_existing and os.path.exists(out_path):
                    task.result = out_path
                    task.status = "skipped"
                    return task

                image = read_raster_data(img_path, preserve_dtype=True)
                processing_result = core.process(image, operator_id, base_params)
                save_raster_result(img_path, processing_result.image, out_path, color_order="RGB")
                task.params["metrics"] = processing_result.metrics
                task.result = out_path
                task.status = "done"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.error(f"批量图像处理失败[{img_path}]: {e}", exc_info=True)
            finally:
                task.duration = time.time() - started
            return task

        return self._execute_batch(images, process_one, result, "batch_image_process")

    def _execute_batch(
        self,
        images: List[str],
        worker: Callable[[str], BatchTask],
        result: BatchResult,
        task_type: str = "batch",
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
                elif task.status == "skipped":
                    result.skipped += 1
                else:
                    result.failed += 1
                current = result.success + result.failed + result.skipped
                self._report_task(task, current, total)
                self._report_progress(current, total, f"{task_type}: {Path(task.input_path).name}")

        result.end_time = time.time()
        logger.info(
            f"批量处理完成: {total} 个任务, 成功 {result.success}, "
            f"跳过 {result.skipped}, 失败 {result.failed}, 耗时 {result.elapsed:.1f}s"
        )
        return result

    def export_summary(
        self,
        result: BatchResult,
        output_dir: str,
        filename_prefix: str = "summary",
    ) -> Dict[str, str]:
        """Export machine-readable JSON/CSV summaries for a batch result."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        safe_prefix = filename_prefix.strip() or "summary"
        json_path = os.path.join(output_dir, f"{safe_prefix}.json")
        csv_path = os.path.join(output_dir, f"{safe_prefix}.csv")
        failed_csv_path = os.path.join(output_dir, f"{safe_prefix}_failed.csv")

        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": result.total,
            "success": result.success,
            "skipped": result.skipped,
            "failed": result.failed,
            "elapsed": result.elapsed,
            "success_rate": result.success_rate,
            "tasks": [asdict(task) for task in result.tasks],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "input_path",
                    "output_dir",
                    "status",
                    "result",
                    "error",
                    "duration",
                    "params",
                ],
            )
            writer.writeheader()
            for task in result.tasks:
                row = asdict(task)
                row["params"] = json.dumps(row.get("params", {}), ensure_ascii=False)
                writer.writerow(row)

        failed_tasks = [task for task in result.tasks if task.status == "failed"]
        if failed_tasks:
            with open(failed_csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["input_path", "output_dir", "error", "duration", "params"],
                )
                writer.writeheader()
                for task in failed_tasks:
                    row = asdict(task)
                    row["params"] = json.dumps(row.get("params", {}), ensure_ascii=False)
                    writer.writerow(
                        {
                            "input_path": row["input_path"],
                            "output_dir": row["output_dir"],
                            "error": row["error"],
                            "duration": row["duration"],
                            "params": row["params"],
                        }
                    )

        paths = {"json": json_path, "csv": csv_path}
        if failed_tasks:
            paths["failed_csv"] = failed_csv_path
        return paths
