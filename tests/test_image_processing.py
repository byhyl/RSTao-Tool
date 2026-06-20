import cv2
import numpy as np

from core.image_processing import ImageProcessingCore, match_histogram


def test_linear_stretch_outputs_uint8():
    core = ImageProcessingCore()
    image = np.arange(100, dtype=np.uint16).reshape(10, 10)

    result = core.process(image, "linear_stretch", {"low_percent": 0, "high_percent": 100})

    assert result.image.dtype == np.uint8
    assert result.image.min() == 0
    assert result.image.max() == 255


def test_canny_extracts_edges():
    core = ImageProcessingCore()
    image = np.zeros((32, 32), dtype=np.uint8)
    image[8:24, 8:24] = 255

    result = core.process(image, "canny", {"threshold1": 50, "threshold2": 100, "aperture": "3"})

    assert result.image.dtype == np.uint8
    assert np.count_nonzero(result.image) > 0


def test_pca_component_for_multiband_image():
    core = ImageProcessingCore()
    x = np.tile(np.arange(12, dtype=np.float32), (12, 1))
    y = x.T
    image = np.dstack([x, y, x + y])

    result = core.process(image, "pca", {"component": 1})

    assert result.image.shape == image.shape[:2]
    assert result.image.dtype == np.uint8
    assert 0 <= result.metrics["explained_ratio"] <= 1


def test_reference_histogram_match_changes_distribution():
    source = np.zeros((16, 16), dtype=np.uint8)
    source[:, 8:] = 40
    reference = np.zeros((16, 16), dtype=np.uint8)
    reference[:, 8:] = 220

    matched = match_histogram(source, reference)

    assert matched.shape == source.shape
    assert matched.max() > source.max()


def test_gradient_direction_is_displayable():
    core = ImageProcessingCore()
    image = np.zeros((20, 20), dtype=np.uint8)
    cv2.line(image, (2, 2), (17, 17), 255, 2)

    result = core.process(image, "gradient", {"mode": "direction", "ksize": 3})

    assert result.image.dtype == np.uint8
    assert result.image.shape == image.shape


def test_otsu_active_parameters_hide_manual_threshold_inputs():
    core = ImageProcessingCore()

    active = core.active_parameters("threshold", {"method": "otsu"})

    assert [param.name for param in active] == ["method"]


def test_threshold_active_parameters_follow_selected_method():
    core = ImageProcessingCore()

    binary = core.active_parameters("threshold", {"method": "Binary(固定阈值)"})
    adaptive = core.active_parameters("threshold", {"method": "Adaptive Mean(自适应均值)"})

    assert [param.name for param in binary] == ["method", "threshold"]
    assert [param.name for param in adaptive] == ["method", "block_size"]


def test_core_accepts_display_label_for_otsu():
    core = ImageProcessingCore()
    image = np.zeros((32, 32), dtype=np.uint8)
    image[:, 16:] = 255

    result = core.process(image, "threshold", {"method": "OTSU(大津法)"})

    assert result.image.dtype == np.uint8
    assert result.metrics["threshold"] >= 0


def test_rgb_red_converts_to_red_hue():
    core = ImageProcessingCore()
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[:, :] = [255, 0, 0]

    result = core.process(image, "color_space", {"target": "HSV"})

    assert int(result.image[0, 0, 0]) == 0


def test_rgb_grayscale_uses_red_weight():
    core = ImageProcessingCore()
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[:, :] = [255, 0, 0]

    result = core.process(image, "grayscale")

    assert int(result.image[0, 0]) == 76


def test_bilateral_filter_accepts_rgb_image():
    core = ImageProcessingCore()
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[:, :] = [255, 0, 0]

    result = core.process(
        image,
        "bilateral_filter",
        {"diameter": 3, "sigma_color": 20, "sigma_space": 20},
    )

    assert result.image.shape == image.shape
