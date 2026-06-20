from core.spatial_reference import (
    SpatialReference,
    compare_spatial_refs,
    compute_file_hash,
    format_spatial_ref,
    map_to_pixel,
    pixel_to_map,
)


def test_compute_file_hash_is_stable(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"rstao")

    first = compute_file_hash(path)
    second = compute_file_hash(path)

    assert first == second
    assert len(first) == 16


def test_compare_spatial_refs_by_epsg():
    a = SpatialReference(epsg=4326, crs="EPSG:4326")
    b = SpatialReference(epsg=3857, crs="EPSG:3857")

    result = compare_spatial_refs(a, b)

    assert result["compatible"] is False
    assert result["level"] == "error"


def test_format_spatial_ref_contains_epsg_and_bounds():
    ref = SpatialReference(epsg=4326, bounds=(1.0, 2.0, 3.0, 4.0), pixel_size=(0.5, 0.5))

    text = format_spatial_ref(ref)

    assert "EPSG:4326" in text
    assert "Bounds" in text
    assert "Pixel" in text


def test_pixel_map_roundtrip_with_affine_tuple():
    transform = (100.0, 2.0, 0.0, 200.0, 0.0, -2.0)

    mx, my = pixel_to_map(3, 4, transform)
    px, py = map_to_pixel(mx, my, transform)

    assert (mx, my) == (106.0, 192.0)
    assert abs(px - 3) < 1e-9
    assert abs(py - 4) < 1e-9
