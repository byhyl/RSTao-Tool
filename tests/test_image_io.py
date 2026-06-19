"""Image IO metadata tests."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.image_io import get_image_metadata


def test_get_image_metadata_png(tmp_path):
    image_path = tmp_path / "sample.png"
    arr = np.zeros((12, 10, 3), dtype=np.uint8)
    Image.fromarray(arr).save(image_path)

    meta = get_image_metadata(image_path)

    assert meta["width"] == 10
    assert meta["height"] == 12
    assert meta["bands"] == 3
    assert meta["dtype"] == "uint8"
    assert meta["size_bytes"] > 0
