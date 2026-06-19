# User Guide

## Quick Start

1. Launch `RSTao-Tool.exe` (or `python main.py`)
2. Create a new project or open an existing one
3. Use the ribbon menu to switch between modules

## Feature Detection

1. Click **Feature Detection** tab
2. Click **Load Image** to select a remote sensing image
3. Choose detection method: Harris / Moravec / Forstner / SUSAN
4. Adjust parameters with sliders (real-time preview)
5. Click **Save Result** to export

## Image Matching

1. Switch to **Image Matching** tab
2. **Add Template** — select a template image
3. **Load Search Image** — select the target image
4. Choose matching mode: Single / Multi-target
5. Adjust threshold and NMS radius
6. Click **Run Matching**

## Vector Editing

1. Switch to **Vector Editor** tab
2. **Load Base Image** — select a background raster
3. **Load SHP** — import existing shapefiles
4. Use mode buttons:
   - **Draw Point/Line/Polygon** — click on canvas to draw
   - **Move** — drag features
   - **Edit Vertices** — drag individual vertices
   - **Delete** — remove selected feature
5. **Export** to SHP or DXF format

## Coordinate Transform

1. Switch to **Coordinate Transform** tab
2. Load point file (CSV/TXT) or raster image
3. Select source/destination coordinate systems
4. Optionally configure 7-parameter transform
5. Click **Execute** to transform
6. Export results as CSV

## Object Detection

1. Switch to **Object Detection** tab
2. Load an ONNX model file
3. Load an image
4. Adjust confidence threshold
5. Results displayed with bounding boxes

## Batch Processing

1. **Features** → **Batch Processing** in menu
2. Select input directory and output directory
3. Choose processing type (detection or matching)
4. Click **Start** — progress shown in real-time

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save project |
| `Ctrl+N` | New project |
| `Ctrl+O` | Open project |
| `Ctrl+Z` | Undo (vector editing) |
| `Ctrl+Y` | Redo (vector editing) |
| `Delete` | Delete selected feature |
| `Drag & Drop` | Load image/SHP/project file |

## Settings

- **Theme**: Dark / Light mode
- **Language**: Chinese / English
- **Cache Directory**: Temporary file location
- **Default Parameters**: Algorithm presets
