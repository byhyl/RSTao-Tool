"""批量处理器测试"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.batch_processor import BatchProcessor, BatchResult, BatchTask


class TestBatchTask:
    def test_defaults(self):
        t = BatchTask(input_path="test.tif", output_dir="./out")
        assert t.status == "pending"
        assert t.input_path == "test.tif"

    def test_params(self):
        t = BatchTask(input_path="a.tif", output_dir="./out", params={"k": 0.04})
        assert t.params["k"] == 0.04


class TestBatchResult:
    def test_elapsed_zero(self):
        r = BatchResult()
        assert r.elapsed == 0.0

    def test_success_rate(self):
        r = BatchResult(total=10, success=8, failed=2)
        assert r.success_rate == 80.0

    def test_success_rate_zero_total(self):
        r = BatchResult(total=0)
        assert r.success_rate == 0.0

    def test_tasks(self):
        t = BatchTask(input_path="x.tif", output_dir="./out")
        r = BatchResult(total=1, success=1, tasks=[t])
        assert len(r.tasks) == 1


class TestBatchProcessor:
    def test_init(self):
        bp = BatchProcessor(max_workers=2)
        assert bp.SUPPORTED_FORMATS is not None

    def test_supported_formats(self):
        bp = BatchProcessor()
        assert ".tif" in bp.SUPPORTED_FORMATS
        assert ".png" in bp.SUPPORTED_FORMATS
        assert ".jpg" in bp.SUPPORTED_FORMATS

    def test_iter_images_nonexistent(self):
        bp = BatchProcessor()
        paths = list(bp.iter_images("C:/nonexistent_dir_xyz_test"))
        assert paths == []

    def test_progress_callback(self):
        bp = BatchProcessor()
        called = []
        bp.on_progress(lambda c, t, m: called.append((c, t, m)))
        bp._report_progress(5, 10, "testing")
        assert called == [(5, 10, "testing")]

    def test_task_callback(self):
        bp = BatchProcessor()
        task = BatchTask(input_path="x.png", output_dir="./out", status="done")
        called = []
        bp.on_task_update(lambda t, c, total: called.append((t.input_path, c, total)))

        bp._report_task(task, 1, 2)

        assert called == [("x.png", 1, 2)]

    def test_execute_batch_counts_skipped(self, tmp_path):
        bp = BatchProcessor(max_workers=1)
        result = BatchResult(total=2, start_time=0)

        def worker(path):
            status = "skipped" if path.endswith("skip.png") else "done"
            return BatchTask(input_path=path, output_dir=str(tmp_path), status=status)

        out = bp._execute_batch(["ok.png", "skip.png"], worker, result)
        assert out.success == 1
        assert out.skipped == 1
        assert out.failed == 0

    def test_export_summary(self, tmp_path):
        bp = BatchProcessor()
        task = BatchTask(
            input_path="image.png",
            output_dir=str(tmp_path),
            params={"threshold": 0.8},
            status="done",
            result=str(tmp_path / "image_matched.png"),
            duration=0.25,
        )
        result = BatchResult(
            total=1,
            success=1,
            failed=0,
            tasks=[task],
            start_time=1.0,
            end_time=2.0,
        )

        paths = bp.export_summary(result, str(tmp_path))
        assert Path(paths["json"]).exists()
        assert Path(paths["csv"]).exists()
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        assert payload["total"] == 1
        assert payload["tasks"][0]["params"]["threshold"] == 0.8

    def test_export_summary_writes_failed_list(self, tmp_path):
        bp = BatchProcessor()
        task = BatchTask(
            input_path="bad.png",
            output_dir=str(tmp_path),
            params={"threshold": 0.8},
            status="failed",
            error="cannot read",
            duration=0.1,
        )
        result = BatchResult(
            total=1,
            failed=1,
            tasks=[task],
            start_time=1.0,
            end_time=2.0,
        )

        paths = bp.export_summary(result, str(tmp_path))

        assert Path(paths["failed_csv"]).exists()
        assert "cannot read" in Path(paths["failed_csv"]).read_text(encoding="utf-8-sig")

    def test_batch_feature_detect_paths_empty(self, tmp_path):
        bp = BatchProcessor()
        result = bp.batch_feature_detect_paths([], str(tmp_path))

        assert result.total == 0
