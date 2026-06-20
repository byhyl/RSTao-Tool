from core.model_registry import ModelConfig, ModelRegistry, infer_model_config, load_adjacent_class_names


def test_model_registry_roundtrip(tmp_path):
    registry = ModelRegistry(tmp_path / "models.json")
    model_path = tmp_path / "detector.onnx"
    model_path.write_bytes(b"not really onnx")
    config = ModelConfig(
        model_path=str(model_path),
        name="detector",
        class_names=["plane", "ship"],
        input_size=(512, 512),
        confidence=0.3,
    )

    registry.save(config)
    loaded = registry.get(str(model_path))

    assert loaded is not None
    assert loaded.class_names == ["plane", "ship"]
    assert loaded.input_size == (512, 512)
    assert loaded.confidence == 0.3


def test_load_adjacent_class_names(tmp_path):
    model_path = tmp_path / "detector.onnx"
    model_path.write_bytes(b"not really onnx")
    (tmp_path / "classes.txt").write_text("plane\nship\n", encoding="utf-8")

    assert load_adjacent_class_names(model_path) == ["plane", "ship"]


def test_infer_model_config_uses_adjacent_classes_when_onnx_is_unreadable(tmp_path):
    model_path = tmp_path / "detector.onnx"
    model_path.write_bytes(b"not really onnx")
    model_path.with_suffix(".txt").write_text("car\ntruck\n", encoding="utf-8")

    config = infer_model_config(str(model_path), confidence=0.4, iou_threshold=0.2)

    assert config.name == "detector"
    assert config.class_names == ["car", "truck"]
    assert config.confidence == 0.4
    assert config.iou_threshold == 0.2
