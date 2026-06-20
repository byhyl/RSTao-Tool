from pathlib import Path

from common.version import APP_VERSION


def test_installer_version_matches_runtime_version():
    setup_text = Path("installer/setup.iss").read_text(encoding="utf-8")

    assert f'#define MyAppVersion "{APP_VERSION}"' in setup_text
