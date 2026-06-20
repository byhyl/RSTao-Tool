import cv2
import numpy as np

from core.batch_processor import BatchProcessor


def _write_image(path, image):
    ok, encoded = cv2.imencode(path.suffix, image)
    assert ok
    encoded.tofile(str(path))


def test_batch_image_process_paths(tmp_path):
    input_path = tmp_path / "input.png"
    image = np.zeros((24, 24, 3), dtype=np.uint8)
    image[6:18, 6:18] = 200
    _write_image(input_path, image)

    output_dir = tmp_path / "out"
    processor = BatchProcessor(max_workers=1)

    result = processor.batch_image_process_paths(
        [str(input_path)],
        str(output_dir),
        "grayscale",
        output_ext=".png",
    )

    assert result.total == 1
    assert result.success == 1
    assert result.failed == 0
    assert (output_dir / "input_grayscale.png").exists()
