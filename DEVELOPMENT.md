# Development Guide

## Environment Setup

```bash
# Create conda environment
conda create -n rstao python=3.10 -y
conda activate rstao

# Install with dev dependencies
pip install -e ".[dev,geo,ml]"
```

## Architecture

```
main.py ──► auth.py (license check) ──► activation_ui.py (if needed)
         └─► ui.MainWindow ──► ui/tabs (Feature/Match/Vector/Coordinate/Detection/Settings)

core/  — pure Python algorithms, no UI dependencies
data/  — file I/O (image, vector), no UI dependencies
 ui/  — CustomTkinter GUI components, depends on core/ and data/
```

## Key Design Decisions

- **No circular imports**: `core/` and `data/` never import from `ui/`
- **License as entry gate**: `main.py` checks auth before any UI is created
- **Plugin system**: `PluginManager` in `core/` supports hot-loading via `importlib`
- **Shapely caching**: `vector_processing` maintains `_shapely_cache` per layer for O(1) hit testing

## Running Tests

```bash
pytest tests/ -v --tb=short --cov=. --cov-report=term-missing
```

## Code Style

```bash
black --line-length 100 --exclude "_admin_repo|tests|server|build|dist" .
isort --profile black --skip _admin_repo --skip tests --skip server .
```

## Adding a Plugin

1. Create folder under `plugins/<plugin_id>/`
2. Create `plugin.json` with metadata
3. Implement `BasePlugin` subclass
4. Restart — plugin auto-discovered

```python
# plugins/my_plugin/my_plugin.py
from core.plugin_manager import BasePlugin, PluginInfo

class MyPlugin(BasePlugin):
    def info(self) -> PluginInfo:
        return PluginInfo(id="my_plugin", name="My Plugin", ...)

    def on_load(self, context) -> bool:
        return True
```

## Building EXE

```bash
pyinstaller --onefile --windowed --name RSTao-Tool --icon assets/icon.ico main.py
```
