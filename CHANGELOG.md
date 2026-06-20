# Changelog

## [2.1.0] — 2026-06-05

### Architecture
- Split `main.py` (536→34 lines) into `auth.py` + `activation_ui.py`
- Split `admin_tool.py` (974→521 lines) into modular tabs
- Extracted `LicenseManager` to `ui/license_info.py`
- Removed 3 duplicate method definitions in `main_window.py`

### Performance
- Shapely geometry caching in `select_feature` (O(n)→O(1) per click)
- RasterViewer frame cache (LRU, 3 frames)
- Batch processor: `iter_images()` generator + `limit` parameter

### Security
- Activation server admin-token endpoint rate limiting
- Activation logs truncate device fingerprints in success messages
- Legacy AES licenses disabled by default; v2 RSA-signed licenses preferred

### Testing
- Added `test_coordinate_system.py` (17 tests)
- Added `test_vector_processing.py` (19 tests)
- Added Shapely cache tests (4 tests)
- Total: 29 → **69 tests**

### UI/UX
- Undo/Redo command stack (Ctrl+Z/Y, 50-step history)
- Keyboard shortcuts: Ctrl+S/N/O, Delete
- Drag & drop file loading (.tif/.shp/.rstao)
- RasterViewer right-click menu (Fit/Zoom 1:1/Export)
- Settings persistence (`RSTao_Data/settings/settings.json`)
- i18n expansion: 30 → **76 keys**
- `settings_tab.py` fully i18n-ed

### Build
- CI: Python 3.10/11/12 matrix, coverage reports
- Separate `publish.yml` for tagged releases
- Fixed bare `except:` → `except Exception:` (5 locations)
- Fixed `print()` → `logger` (16 locations)
- Unified dependencies in `pyproject.toml` with `[dev]`/`[geo]`/`[ml]` groups

### Data
- Project file `schema_version: 4`
- Auto-backup `.bak` before save

## [2.0.0] — Initial Release
- Core features: feature detection, image matching, vector editing, coordinate transform
- ONNX object detection support
- Batch processing engine
- Plugin system
- License activation (online + offline)
