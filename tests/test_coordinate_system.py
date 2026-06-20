"""坐标系统模块测试 — 修正版"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from core.coordinate_system import (
    CHINA_EPSG,
    COMMON_EPSG,
    CoordinateSystem,
    CoordinateTransform,
    PointSet,
    RasterInfo,
    SevenParams,
)


class TestSevenParams:
    def test_default_params_zero(self):
        p = SevenParams()
        assert p.dx == 0.0 and p.dy == 0.0 and p.dz == 0.0

    def test_to_matrix_shape(self):
        p = SevenParams(dx=10, dy=-5, dz=3, rx=1.5, ry=-0.8, rz=2.1, scale=5.0)
        m = p.to_matrix()
        assert m.shape == (4, 4)
        np.testing.assert_array_almost_equal(m[3], [0, 0, 0, 1])

    def test_zero_params_is_identity(self):
        p = SevenParams()
        m = p.to_matrix()
        np.testing.assert_array_almost_equal(m, np.eye(4))

    def test_translation_only(self):
        p = SevenParams(dx=100, dy=200, dz=0)
        m = p.to_matrix()
        assert m[0, 3] == 100 and m[1, 3] == 200 and m[2, 3] == 0

    def test_preset_known(self):
        p = SevenParams.preset("BJ54_to_WGS84")
        assert p.dx != 0 or p.dy != 0  # 非零预设

    def test_preset_unknown_returns_default(self):
        p = SevenParams.preset("nonexistent_preset_xyz")
        assert p.dx == 0.0  # 返回默认零值


class TestCoordinateTransform:
    def test_is_dataclass(self):
        t = CoordinateTransform(src_epsg=4326, dst_epsg=3857)
        assert t.src_epsg == 4326
        assert t.dst_epsg == 3857

    def test_with_seven_params(self):
        params = SevenParams(dx=10, dy=-5, dz=3)
        t = CoordinateTransform(
            src_epsg=4326,
            dst_epsg=4490,
            src_name="WGS84",
            dst_name="CGCS2000",
            seven_params=params,
        )
        assert t.seven_params.dx == 10
        assert t.src_name == "WGS84"


class TestCoordinateSystem:
    def test_list_all_returns_dict(self):
        epsg = CoordinateSystem.list_all()
        assert isinstance(epsg, dict)

    def test_common_epsg_values(self):
        assert COMMON_EPSG["WGS84"] == 4326
        assert COMMON_EPSG["CGCS2000"] == 4490

    def test_china_epsg_not_empty(self):
        assert len(CHINA_EPSG) > 0

    def test_auto_detect_utm_beijing(self):
        cs = CoordinateSystem()
        epsg = cs.auto_detect_utm(116.4, 39.9)
        assert isinstance(epsg, int)
        assert epsg > 0  # returns EPSG code

    def test_wgs84_to_projection(self):
        cs = CoordinateSystem()
        if cs.available:
            result = cs.wgs84_to_projection(116.4, 39.9, 3857)
            assert result is not None and len(result) == 2

    def test_parse_csv_without_header_keeps_all_points(self, tmp_path):
        path = tmp_path / "points.csv"
        path.write_text("116.1,39.1\n116.2,39.2\n", encoding="utf-8")

        ps = CoordinateSystem().parse_point_file(str(path))

        assert ps.points == [(116.1, 39.1), (116.2, 39.2)]
        assert ps.names == ["P1", "P2"]


class TestPointSet:
    def test_default_values(self):
        ps = PointSet()
        assert ps.points == []
        assert ps.names == []
        assert ps.source_file == ""

    def test_with_points(self):
        ps = PointSet(points=[(1.0, 2.0)], names=["A"], source_file="test.csv")
        assert len(ps.points) == 1


class TestRasterInfo:
    def test_default_values(self):
        ri = RasterInfo()
        assert ri.width == 0
        assert ri.height == 0
        assert ri.epsg == 0

    def test_with_data(self):
        ri = RasterInfo(width=1024, height=768, bands=3, crs="EPSG:4326", epsg=4326)
        assert ri.width == 1024
        assert ri.bands == 3
