"""Input preflight inspection tests."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.input_inspector import inspect_file, inspect_points_file


def test_inspect_image_png(tmp_path):
    path = tmp_path / "demo.png"
    Image.fromarray(np.zeros((8, 10, 3), dtype=np.uint8)).save(path)

    result = inspect_file(path)

    assert result.can_import
    assert result.kind == "image"
    assert ("尺寸", "10 x 8") in result.summary


def test_inspect_points_file_without_header(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text("116.1,39.1\n116.2,39.2\n", encoding="utf-8")

    result = inspect_points_file(path)

    assert result.can_import
    assert ("有效点数", "2") in result.summary
    assert any("前两列" in warning for warning in result.warnings)


def test_inspect_missing_file_blocks_import(tmp_path):
    result = inspect_file(tmp_path / "missing.tif")

    assert not result.can_import
    assert result.title == "文件不存在"
