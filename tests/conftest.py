import pytest


@pytest.fixture(autouse=True)
def isolate_runtime_data(tmp_path, monkeypatch):
    """Keep tests from writing user-facing portable runtime data."""
    monkeypatch.setenv("RSTAO_DATA_DIR", str(tmp_path / "RSTao_Data"))
