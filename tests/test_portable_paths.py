from pathlib import Path

from common import paths


def test_portable_data_dir_prefers_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("RSTAO_DATA_DIR", raising=False)
    monkeypatch.delenv("RSTAO_PORTABLE_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "get_runtime_dir", lambda: tmp_path / "app")

    data_dir = paths.get_portable_data_dir()

    assert data_dir == tmp_path / "app" / "RSTao_Data"
    assert paths.resolve_license_path() == data_dir / "license" / ".license.dat"
    assert paths.get_settings_dir() == data_dir / "settings"
    assert paths.get_logs_dir() == data_dir / "logs"
    assert paths.get_temp_dir() == data_dir / "temp"
    assert paths.get_cache_dir() == data_dir / "cache"
    assert paths.get_admin_data_dir() == data_dir / "admin"
    assert paths.get_server_data_dir() == data_dir / "server"


def test_portable_data_dir_falls_back_when_runtime_is_not_writable(tmp_path, monkeypatch):
    monkeypatch.delenv("RSTAO_DATA_DIR", raising=False)
    monkeypatch.delenv("RSTAO_PORTABLE_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "get_runtime_dir", lambda: tmp_path / "locked_app")
    monkeypatch.setattr(paths, "_is_writable_dir", lambda _path: False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))

    data_dir = paths.get_portable_data_dir()

    assert data_dir == tmp_path / "AppData" / "RSTao-Tool" / "RSTao_Data"
    assert data_dir.exists()


def test_migrate_file_once_copies_without_deleting_source(tmp_path):
    old_file = tmp_path / "old" / ".license.dat"
    old_file.parent.mkdir()
    old_file.write_text("license-key", encoding="utf-8")
    new_file = tmp_path / "app" / "RSTao_Data" / "license" / ".license.dat"

    migrated_from = paths.migrate_file_once([old_file], new_file)

    assert migrated_from == old_file
    assert old_file.exists()
    assert new_file.read_text(encoding="utf-8") == "license-key"


def test_migrate_file_once_does_not_overwrite_existing_target(tmp_path):
    old_file = tmp_path / "old" / "settings.json"
    old_file.parent.mkdir()
    old_file.write_text('{"theme": "light"}', encoding="utf-8")
    new_file = tmp_path / "new" / "settings.json"
    new_file.parent.mkdir()
    new_file.write_text('{"theme": "dark"}', encoding="utf-8")

    migrated_from = paths.migrate_file_once([old_file], new_file)

    assert migrated_from is None
    assert new_file.read_text(encoding="utf-8") == '{"theme": "dark"}'
