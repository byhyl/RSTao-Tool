from core.resource_catalog import load_resource_catalog, record_resource


def test_record_resource_writes_latest_entry_first(tmp_path):
    catalog_path = tmp_path / "resources.json"
    first = {"resource_id": "r1", "name": "old.tif", "source_path": "old.tif"}
    updated = {"resource_id": "r1", "name": "new.tif", "source_path": "new.tif"}
    second = {"resource_id": "r2", "name": "points.pcd", "source_path": "points.pcd"}

    record_resource(first, catalog_path)
    record_resource(second, catalog_path)
    record_resource(updated, catalog_path)

    catalog = load_resource_catalog(catalog_path)

    assert [item["resource_id"] for item in catalog] == ["r1", "r2"]
    assert catalog[0]["name"] == "new.tif"
    assert catalog[0]["catalog_updated_at"]
