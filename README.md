# RSTao-Tool

**Remote Sensing Image Processing & Vector Editing Platform**

A professional-grade Windows desktop application for GIS/Remote Sensing professionals, built with Python + OpenCV + CustomTkinter.

## Features

| Module | Description |
|--------|-------------|
| **Feature Detection** | Harris, Moravec, Forstner, SUSAN corner detectors, SIFT/ORB/HOG |
| **Image Matching** | NCC template matching, multi-target matching, NMS |
| **Vector Editor** | Create/edit Point/Line/Polygon features, SHP import/export, DXF export |
| **Coordinate System** | Bursa-Wolf 7-parameter transform, China EPSG presets, point file parsing |
| **Object Detection** | ONNX Runtime inference (YOLOv5/v8/v11) |
| **Batch Processing** | Multi-threaded batch engine for feature detection and image matching |
| **Report Export** | HTML reports with statistics and charts |
| **Plugin System** | Extensible plugin architecture |

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.10+
- conda/pip

### Install

```bash
git clone https://github.com/byhyl/RSTao-Tool.git
cd RSTao-Tool
pip install -e ".[dev]"     # development
pip install -e ".[dev,geo,ml]"  # full install with geospatial + ML
```

### Run

```bash
# Main application
python main.py

# Admin tool (license management)
python admin_tool.py
```

### License Signing Key

The current license format uses RSA-signed v2 license keys. Keep the private key outside the client package and configure the admin tool/server with one of:

```bash
set RSTAO_LICENSE_PRIVATE_KEY_FILE=C:\secure\admin_license_private.pem
set RSTAO_LICENSE_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..."
```

For local development, `admin_license_private.pem` in the repository root is also detected automatically, but it is ignored by Git and must be backed up securely. Legacy AES licenses are disabled by default; set `RSTAO_ALLOW_LEGACY_LICENSE=1` only during migration.

## Project Structure

```
RSTao-Tool/
├── main.py              # Entry point
├── auth.py              # License authentication
├── activation_ui.py     # Activation window
├── admin_tool/          # License management (admin panel)
│   └── tabs/            # Tab modules
├── common/              # Shared utilities (crypto, logger, i18n)
├── core/                # Core algorithms (no UI)
├── data/                # I/O layer (image, vector)
├── ui/                  # GUI components
├── server/              # Activation server
├── tests/               # Unit tests (69+)
├── i18n/                # zh/en translations
├── plugins/             # Plugin directory
└── docs/                # Documentation
```

## License

Proprietary. All rights reserved.
