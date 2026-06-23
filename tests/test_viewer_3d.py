"""Tests for the 3D module (core, non-GUI components)."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from core.gpu_accel import (
    build_cupy_install_command,
    format_gpu_setup_plan,
    get_cupy,
    get_gpu_status,
    parse_nvidia_smi_output,
    recommend_cupy_package,
)
from core.mesh_ops import boundary_edges_from_faces, mesh_quality_report
from core.pointcloud_io import export_las
from core.pointcloud_ops import (
    PointCloudData,
    build_classification_colors,
    classify_ground,
    clip_by_plane_data,
    crop_by_bounds_data,
    crop_by_polygon_data,
    estimate_normals,
    farthest_point_sample,
    local_roughness_curvature,
    nearest_point,
    normalize_height,
    pointcloud_to_grids,
    smrf_filter_data,
    to_o3d_pointcloud,
    voxel_downsample_data,
)
from core.scene_graph import (
    ColorMode,
    LayerType,
    SceneGraph,
    SceneLayer,
    apply_colormap,
    get_classification_color,
)
from core.terrain_analysis import aspect, hillshade, slope
from ui.viewer_3d_lod import LODManager, OctreeNode
from ui.viewer_3d_state import Viewer3DStateManager
from ui.viewer_3d_tasks import Viewer3DTask
from ui.viewer_3d_toolbar import MeasurementTool, SectionTool


def _sample_cloud() -> PointCloudData:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.1, 0.1, 0.2],
            [1.0, 0.0, 1.0],
            [2.0, 2.0, 2.0],
        ],
        dtype=np.float64,
    )
    colors = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    classes = np.array([2, 2, 6, 1], dtype=np.int32)
    intensities = np.array([10, 20, 30, 40], dtype=np.float32)
    return PointCloudData(
        points,
        colors=colors,
        classifications=classes,
        intensities=intensities,
    )


class TestSceneGraph:
    def test_add_remove_layer(self):
        sg = SceneGraph()
        layer = SceneLayer(name="test", layer_type=LayerType.POINT_CLOUD)
        lid = sg.add_layer(layer)
        assert len(sg.layers) == 1
        assert sg.get_layer(lid) is layer
        assert sg.remove_layer(lid)
        assert len(sg.layers) == 0

    def test_visible_layers(self):
        sg = SceneGraph()
        l1 = SceneLayer(name="a", visible=True)
        l2 = SceneLayer(name="b", visible=False)
        sg.add_layer(l1)
        sg.add_layer(l2)
        assert len(sg.get_visible_layers()) == 1

    def test_serialization_roundtrip(self):
        sg = SceneGraph(scene_crs="EPSG:4326")
        layer = SceneLayer(
            name="test_layer",
            layer_type=LayerType.MESH,
            source_path="/tmp/test.obj",
            face_count=100,
        )
        sg.add_layer(layer)
        data = sg.to_dict()
        sg2 = SceneGraph.from_dict(data)
        assert sg2.scene_crs == "EPSG:4326"
        assert len(sg2.layers) == 1
        assert sg2.layers[0].name == "test_layer"


class TestColorUtilities:
    def test_classification_color_known(self):
        c = get_classification_color(2)
        assert c == (0.35, 0.55, 0.25)

    def test_classification_color_unknown(self):
        c = get_classification_color(99)
        assert c == (0.5, 0.5, 0.5)

    def test_apply_colormap(self):
        vals = np.array([0.0, 0.5, 1.0], dtype=np.float32)
        colors = apply_colormap(vals, "viridis")
        assert colors.shape == (3, 3)
        assert colors.dtype == np.float32
        assert 0 <= colors.min() <= 1
        assert 0 <= colors.max() <= 1

    def test_build_classification_colors(self):
        ids = np.array([2, 6, 2, 7], dtype=np.int32)
        colors = build_classification_colors(ids)
        assert colors.shape == (4, 3)
        np.testing.assert_array_almost_equal(colors[0], colors[2])


class TestPointcloudOps:
    def test_pointcloud_data_subset_copy_and_padding(self):
        data = _sample_cloud()
        subset = data.subset(np.array([0, 2], dtype=np.int64))
        assert subset.points.shape == (2, 3)
        np.testing.assert_array_equal(subset.classifications, np.array([2, 6]))
        copied = subset.copy()
        copied.points[0, 0] = 999
        assert subset.points[0, 0] == 0

        padded = PointCloudData(np.array([[1.0, 2.0]]))
        assert padded.points.shape == (1, 3)
        assert padded.points[0, 2] == 0

    def test_voxel_downsample_data_preserves_attributes(self):
        data = _sample_cloud()
        down = voxel_downsample_data(data, voxel_size=0.5)
        assert len(down.points) == 3
        assert down.colors is not None and down.colors.shape == (3, 3)
        assert down.classifications is not None
        assert down.intensities is not None
        assert 2 in down.classifications
        assert down.metadata["source_point_count"] == len(data.points)
        assert down.metadata["compute_backend"] == "cpu"

    def test_gpu_acceleration_falls_back_or_matches_cpu(self):
        data = _sample_cloud()
        status = get_gpu_status("auto")
        cp, cupy_status = get_cupy("auto")

        down_cpu = voxel_downsample_data(data, voxel_size=0.5, use_gpu=False)
        down_auto = voxel_downsample_data(data, voxel_size=0.5, use_gpu=True)
        assert len(down_auto.points) == len(down_cpu.points)
        assert down_auto.colors is not None
        assert down_auto.classifications is not None
        assert down_auto.metadata["compute_backend"] in {"cpu", "cupy"}
        if cp is None:
            assert status.available is False or cupy_status.available is False
            assert down_auto.metadata["compute_backend"] == "cpu"

        grids_cpu = pointcloud_to_grids(data, cell_size=0.5, use_gpu=False)
        grids_auto = pointcloud_to_grids(data, cell_size=0.5, use_gpu=True)
        assert grids_auto["compute_backend"] in {"cpu", "cupy"}
        np.testing.assert_allclose(grids_auto["dem"], grids_cpu["dem"], equal_nan=True)
        np.testing.assert_allclose(grids_auto["dsm"], grids_cpu["dsm"], equal_nan=True)
        np.testing.assert_array_equal(grids_auto["count"], grids_cpu["count"])

    def test_gpu_setup_helpers(self):
        parsed = parse_nvidia_smi_output(
            "NVIDIA-SMI 555.85 Driver Version: 555.85 CUDA Version: 12.5"
        )
        assert parsed["cuda_version"] == "12.5"
        assert parsed["driver_version"] == "555.85"
        assert recommend_cupy_package("12.5") == "cupy-cuda12x[ctk]<14"
        assert recommend_cupy_package("13.0") == "cupy-cuda12x[ctk]<14"
        assert recommend_cupy_package("11.8") == ""

        command = build_cupy_install_command("cupy-cuda12x[ctk]<14")
        assert command[-3:] == ("install", "-U", "cupy-cuda12x[ctk]<14")

        class Plan:
            summary = "检测到 CUDA 12.5"
            recommended_package = "cupy-cuda12x[ctk]<14"
            pip_args = command
            steps = ("安装后复检",)

            class status:
                available = False
                reason = "missing cupy"

            class cuda_info:
                gpu_name = "RTX"
                driver_version = "555.85"
                cuda_version = "12.5"

        text = format_gpu_setup_plan(Plan)
        assert "cupy-cuda12x" in text
        assert "missing cupy" in text

    def test_crop_clip_polygon_and_nearest(self):
        data = _sample_cloud()
        inside, outside = crop_by_bounds_data(
            data,
            np.array([-0.1, -0.1, -0.1]),
            np.array([1.1, 1.1, 1.1]),
        )
        assert len(inside.points) == 3
        assert len(outside.points) == 1

        polygon = np.array([[-0.5, -0.5], [1.5, -0.5], [1.5, 1.5], [-0.5, 1.5]])
        poly_in, poly_out = crop_by_polygon_data(data, polygon)
        assert len(poly_in.points) == 3
        assert len(poly_out.points) == 1

        upper, lower = clip_by_plane_data(data, np.array([0, 0, 0.5]), np.array([0, 0, 1]))
        assert len(upper.points) == 2
        assert len(lower.points) == 2

        idx, dist = nearest_point(data.points, np.array([0.11, 0.1, 0.2]))
        assert idx == 1
        assert dist < 0.02

    def test_grids_ground_classification_and_height_normalization(self):
        ground_points = np.array([[x, y, 0.0] for x in range(3) for y in range(3)], dtype=float)
        object_points = np.array([[1.0, 1.0, 2.0], [2.0, 2.0, 3.0]], dtype=float)
        data = PointCloudData(np.vstack([ground_points, object_points]))

        grids = pointcloud_to_grids(data, cell_size=1.0)
        assert grids["dem"].shape == (3, 3)
        assert grids["dsm"][1, 1] == 2.0
        assert grids["chm"][1, 1] == 2.0
        assert grids["count"][1, 1] == 2

        ground, non_ground = smrf_filter_data(data, cell_size=1.0, height_threshold=0.25)
        assert len(ground.points) >= 9
        assert len(non_ground.points) <= 2

        classified = classify_ground(data, ground, non_ground)
        assert classified.classifications is not None
        assert np.count_nonzero(classified.classifications == 2) == len(ground.points)

        normalized = normalize_height(data, ground, cell_size=1.0)
        assert normalized.metadata["height_normalized"] is True
        assert normalized.points[:, 2].min() == 0

    def test_local_roughness_curvature(self):
        pts = np.array([[x, y, float(x + y)] for x in range(4) for y in range(4)], dtype=float)
        roughness, curvature = local_roughness_curvature(pts, k=6)
        assert roughness.shape == (len(pts),)
        assert curvature.shape == (len(pts),)
        assert np.all(curvature >= 0)

    def test_farthest_point_sample(self):
        pts = np.random.default_rng(0).random((1000, 3)).astype(np.float32)
        idx = farthest_point_sample(pts, 10)
        assert len(idx) == 10
        assert idx.dtype == np.int64

    def test_fps_all_points(self):
        pts = np.random.default_rng(1).random((5, 3)).astype(np.float32)
        idx = farthest_point_sample(pts, 10)
        assert len(idx) == 5

    def test_estimate_normals_generates_normals(self):
        pytest.importorskip("open3d")
        pts = np.random.default_rng(2).random((100, 3)).astype(np.float64)
        pcd = to_o3d_pointcloud(pts)
        out = estimate_normals(pcd)
        assert out.has_normals()
        assert len(np.asarray(out.normals)) == len(pts)


class TestPointcloudIO:
    def test_export_las_preserves_crs_classification_and_colors(self, tmp_path):
        laspy = pytest.importorskip("laspy")
        pytest.importorskip("pyproj")
        points = np.array(
            [
                [120.0, 30.0, 10.0],
                [120.1, 30.1, 12.0],
                [120.2, 30.2, 14.0],
            ],
            dtype=np.float64,
        )
        classes = np.array([2, 6, 1], dtype=np.uint8)
        colors = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )
        path = tmp_path / "sample.las"

        assert export_las(points, path, classifications=classes, colors=colors, crs_wkt="EPSG:4326")

        las = laspy.read(path)
        assert len(las.points) == len(points)
        np.testing.assert_array_equal(np.asarray(las.classification), classes)
        assert int(las.red[0]) == 65535
        assert int(las.green[1]) == 65535
        crs = las.header.parse_crs()
        assert crs is not None
        assert crs.to_epsg() == 4326


class TestTerrainAnalysis:
    def test_slope_shape(self):
        dem = np.random.default_rng(3).random((64, 64)).astype(np.float32) * 100
        slp = slope(dem, cell_size=30.0)
        assert slp.shape == dem.shape
        assert slp.min() >= 0

    def test_aspect_range(self):
        dem = np.random.default_rng(4).random((32, 32)).astype(np.float32) * 50 + 10
        asp = aspect(dem, cell_size=10.0)
        assert asp.shape == dem.shape

    def test_hillshade_range(self):
        dem = np.random.default_rng(5).random((48, 48)).astype(np.float32) * 200
        hs = hillshade(dem, azimuth=315, altitude=45)
        assert hs.shape == dem.shape
        assert 0 <= hs.min() <= 1
        assert 0 <= hs.max() <= 1


class TestLODManager:
    def test_build_query_detail_and_classification_mapping(self):
        mgr = LODManager(max_points_per_frame=300, min_points_per_node=50, max_depth=4)
        rng = np.random.default_rng(6)
        pts = rng.random((1000, 3)).astype(np.float32) * 100
        colors = rng.random((1000, 3)).astype(np.float32)
        classes = (np.arange(1000) % 5).astype(np.int32)

        root = mgr.build("test_layer", pts, colors=colors, classifications=classes)
        assert root is not None
        assert root.has_points()

        camera = np.array([50, 50, 250], dtype=np.float32)
        view_dir = np.array([0, 0, -1], dtype=np.float32)
        detail = mgr.query_detail("test_layer", camera, view_dir)
        assert 0 < len(detail.points) <= 300
        assert detail.indices.dtype == np.int64
        assert np.all(detail.indices < len(pts))
        np.testing.assert_array_equal(detail.classifications, classes[detail.indices])

        result_pts, result_colors = mgr.query("test_layer", camera, view_dir)
        assert result_pts.shape[0] == len(detail.points)
        assert result_colors is not None

    def test_cleanup_and_render_budget(self):
        mgr = LODManager(max_points_per_frame=10)
        pts = np.random.default_rng(7).random((20, 3)).astype(np.float32)
        classes = np.arange(20, dtype=np.int32)
        mgr.build("layer", pts, classifications=classes)
        mgr.set_render_budget(5)
        assert mgr.max_points_per_frame == 5
        assert mgr.get_full_classifications("layer") is not None
        mgr.remove_layer("layer")
        assert mgr.get_full_points("layer") is None
        assert mgr.get_full_classifications("layer") is None
        mgr.build("layer2", pts, classifications=classes)
        mgr.clear()
        assert mgr.get_full_points("layer2") is None

    def test_octree_leaf(self):
        center = np.array([0, 0, 0], dtype=np.float32)
        node = OctreeNode(center, half=10.0, depth=0)
        node.point_indices = np.arange(100, dtype=np.int64)
        assert node.is_leaf
        assert node.has_points()


class TestMeshOps:
    def test_boundary_edges_and_quality_report(self):
        vertices = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [1, 1, 0],
                [0, 1, 0],
            ],
            dtype=float,
        )
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        edges = boundary_edges_from_faces(faces)
        assert len(edges) == 4

        report = mesh_quality_report((vertices, faces))
        assert report["vertex_count"] == 4
        assert report["face_count"] == 2
        assert report["boundary_edge_count"] == 4
        assert report["watertight"] is False

        tetra_faces = np.array([[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]], dtype=np.int64)
        tetra_vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
        tetra_report = mesh_quality_report((tetra_vertices, tetra_faces))
        assert tetra_report["boundary_edge_count"] == 0
        assert tetra_report["watertight"] is True


class TestViewer3DTask:
    def test_task_success_and_cancel(self):
        done = threading.Event()
        results = []

        def worker(cancel_event):
            return 42

        task = Viewer3DTask("success", worker, lambda result: (results.append(result), done.set()))
        task.start()
        assert done.wait(2.0)
        assert results[-1].value == 42
        assert results[-1].error is None
        assert results[-1].elapsed_ms >= 0

        cancel_done = threading.Event()
        cancel_results = []

        def slow_worker(cancel_event):
            while not cancel_event.is_set():
                time.sleep(0.005)
            return "cancelled"

        cancel_task = Viewer3DTask(
            "cancel",
            slow_worker,
            lambda result: (cancel_results.append(result), cancel_done.set()),
        )
        cancel_task.start()
        cancel_task.cancel()
        assert cancel_done.wait(2.0)
        assert cancel_results[-1].cancelled is True
        assert cancel_results[-1].value == "cancelled"

    def test_task_progress_callback(self):
        done = threading.Event()
        results = []
        progress_events = []

        def worker(cancel_event, progress):
            progress(0.5, "halfway", "compute")
            return "ok"

        task = Viewer3DTask(
            "progress",
            worker,
            lambda result: (results.append(result), done.set()),
            lambda event: progress_events.append(event),
        )
        task.start()
        assert done.wait(2.0)
        assert results[-1].value == "ok"
        assert any(event.stage == "compute" for event in progress_events)
        assert any(event.text == "halfway" for event in progress_events)
        assert all(0.0 <= event.value <= 1.0 for event in progress_events)


class TestStateManager:
    def test_undo_redo(self):
        sg = SceneGraph()
        mgr = Viewer3DStateManager(max_history=10)

        l1 = SceneLayer(name="layer1")
        sg.add_layer(l1)
        mgr.push(sg)

        l2 = SceneLayer(name="layer2")
        sg.add_layer(l2)
        assert len(sg.layers) == 2

        ok = mgr.undo(sg)
        assert ok
        assert len(sg.layers) == 1

        ok = mgr.redo(sg)
        assert ok
        assert len(sg.layers) == 2


class TestMeasurementTool:
    def test_distance_measurement(self):
        tool = MeasurementTool()
        tool.start(closed=False)
        tool.add_point(np.array([0, 0, 0], dtype=np.float64))
        tool.add_point(np.array([3, 4, 0], dtype=np.float64))
        dist, area = tool.finish()
        assert abs(dist - 5.0) < 0.01
        assert area is None

    def test_area_measurement(self):
        tool = MeasurementTool()
        tool.start(closed=True)
        tool.add_point(np.array([0, 0, 0], dtype=np.float64))
        tool.add_point(np.array([10, 0, 0], dtype=np.float64))
        tool.add_point(np.array([10, 10, 0], dtype=np.float64))
        dist, area = tool.finish()
        assert abs(area - 50.0) < 0.01


class TestSectionTool:
    def test_profile(self):
        dem = np.zeros((100, 100), dtype=np.float32)
        dem[40:60, 40:60] = 10.0
        tool = SectionTool()
        tool.start(np.array([20, 20, 0]))
        tool.update(np.array([80, 80, 0]))
        dists, elevations = tool.sample_profile(dem, num_samples=50)
        assert len(dists) == 50
        assert len(elevations) == 50
        assert elevations.max() > 0
