# ImageProcessingTab UI Polish — Design Spec

**Date:** 2026-06-26
**Status:** Approved (brainstorming complete)
**Scope:** Plan 2 of Phase 5.5 — drag-drop, progress bar, undo (full history stack), presets, slider comparison, zoom sync, batch processing (operator chain + folder)
**Target:** `migration_project/cpp_qt/` and `migration_project/cpp/`

## Goal

Upgrade the `ImageProcessingTab` from a synchronous single-image demo into an
async, undoable, preset-driven, comparison-aware workspace that also supports
batch application of operator chains to a folder of images.

## Confirmed Decisions (from brainstorming)

| Feature | Decision |
|---------|----------|
| Drag-drop | File dropped onto tab = load as input image |
| Progress | Single-image async + determinate progress (requires rstao_core progress callback) |
| Undo | Full history stack, multi-step undo/redo, jump-to-arbitrary-step |
| Presets | Stored in project file via `ProjectModel`; Tab holds `ProjectModel*` |
| Comparison | Slider comparison (single QGraphicsView + dual pixmap + draggable vertical line) |
| Zoom sync | Inherent in single-viewer comparison design (Approach C1) |
| Batch | Operator chain (operator+params per row) + folder input + output to disk folder |

| Architecture choice | Selection |
|---------------------|-----------|
| Async mechanism | A1: `QThread` + `QObject` worker + progress signal |
| History memory | B1: LRU cap of 20 steps, in-memory `cv::Mat` snapshots |
| Comparison render | C1: single `QGraphicsView` + two `QGraphicsPixmapItem` + clip path |

## §1 — Overall Architecture and Component Map

### New / modified components

| Component | Type | Responsibility |
|-----------|------|----------------|
| `ProcessingWorker` | new QObject | Background single-image `rstao::process`; emits `progress` / `finished` / `failed` / `canceled` |
| `BatchWorker` | new QObject | Background chain-over-folder execution; per-file progress; writes to disk |
| `HistoryStack` | new | LRU cap 20 of `{cv::Mat, opId, params, desc}` snapshots; undo/redo/jump |
| `ComparisonView` | new QWidget | Single `QGraphicsView` + dual pixmap + draggable split line; inherent zoom sync |
| `PresetManager` | new | Thin wrapper over `ProjectModel` for preset JSON read/write, grouped by operator |
| `OperatorChainWidget` | new QWidget | Batch chain editor: add/remove rows, each row = operator + params |
| `rstao::ProgressCallback` | new in rstao_core | `std::function<void(int)>`; new `process()` overload accepts it |
| `ImageProcessingTab` | major change | Orchestrates all components; idle/running state machine |

### Data flow

```
User interaction → ImageProcessingTab (state machine)
  ├─ Single Run → ProcessingWorker (bg) → rstao::process(+callback)
  │     → finished signal → HistoryStack.push → ComparisonView.refresh
  ├─ Batch Run → BatchWorker (bg) → per-image chain → disk write
  │     → progress signal → progress bar
  ├─ Undo/Redo → HistoryStack.move → ComparisonView.refresh
  ├─ Preset save → PresetManager → ProjectModel
  └─ Drag-drop → dragEnter/dropEvent → same as onLoadImage
```

### Component boundaries

- `ProcessingWorker` / `BatchWorker`: algorithm + signals only; no UI, no history.
- `HistoryStack`: snapshot array + index only; unaware of UI.
- `ComparisonView`: receives `cv::Mat` to display; runs no algorithm.
- `ProjectModel` is the sole persistence entry for presets; `PresetManager` is a thin façade.

## §2 — rstao_core Progress Callback

### New API (`cpp/include/rstao/image_processing.hpp`)

```cpp
namespace rstao {
using ProgressCallback = std::function<void(int /*percent 0-100*/)>;

// Existing signature preserved
ProcessingResult process(const cv::Mat& src, const std::string& opId,
                         const ParamMap& params = {});
// New overload: with progress callback
ProcessingResult process(const cv::Mat& src, const std::string& opId,
                         const ParamMap& params, ProgressCallback progress);
}
```

### Per-operator progress milestones

| Operator | Milestones |
|----------|-----------|
| grayscale / ihs_intensity / color_space | single step 0→100 |
| smooth / sharpen / threshold / morphology | preprocess 30 → main 70 → 100 |
| edge_detect / linear_stretch | preprocess 25 → core 75 → 100 |
| fft_filter | FFT 40 → frequency filter 70 → inverse 100 |
| pca / normalized_difference | 0→100 |
| histogram_equalization | 0→100 |

### Cancel mechanism

`ProgressCallback` checks an atomic canceled flag; if set, throws
`rstao::OperationCanceled` (new exception type). `ProcessingWorker` catches it
and emits `canceled()`.

### Compatibility

Existing `process(src, opId, params)` signature unchanged; new overload is
independent. Both signatures covered by unit tests.

## §3 — Async Execution and State Machine

### ProcessingWorker (single image)

```cpp
class ProcessingWorker : public QObject {
    Q_OBJECT
public:
    explicit ProcessingWorker(QObject* parent = nullptr);
    void run(const cv::Mat& src, const QString& opId, const rstao::ParamMap& params);
    void cancel();
signals:
    void progress(int percent);
    void finished(rstao::ProcessingResult result, QString opId, rstao::ParamMap params);
    void failed(QString message);
    void canceled();
private:
    QThread* m_thread;
    std::atomic<bool> m_canceled{false};
};
```

- `run()` moves a worker QObject to `m_thread`, `start()`s the thread, returns immediately.
- `ProgressCallback` checks `m_canceled.load()`; if set, throws `OperationCanceled`.
- Main thread: on `finished` → push history → refresh ComparisonView → restore buttons.
- `cancel()` sets flag + quits thread; worker catches exception and emits `canceled()`.

### BatchWorker (batch processing)

```cpp
struct ChainStep {
    QString opId;
    rstao::ParamMap params;
};
struct BatchRequest {
    QStringList inputFiles;
    QString outputDir;
    QVector<ChainStep> chain;
    QString outputFormat;   // "png" | "jpg" | "tif"
};
```

- Per file: read → run each chain step in order via `process(src, step.params, progressCb)` → write to disk.
- Progress = `(completedFiles + inFileProgress) / totalFiles`; emits `progress(int)` and `fileFinished(QString)`.
- Does NOT touch history stack or ComparisonView.
- Cancellable; completed files remain on cancel.

### ImageProcessingTab state machine

| State | Permitted operations |
|-------|---------------------|
| `Idle` | load image, pick operator, adjust params, Run, batch, undo/redo, save preset |
| `SingleRunning` | Cancel only; other buttons disabled; Run button becomes Cancel |
| `BatchRunning` | Cancel only; progress bar shows batch progress |

`updateButtonStates()` refreshes UI on every state transition. Run button reuses
as Cancel (same button, text toggles) to avoid a second button.

## §4 — History Stack

### HistoryStack

```cpp
struct HistoryEntry {
    cv::Mat image;
    QString opId;
    rstao::ParamMap params;
    QString description;
};

class HistoryStack {
public:
    void initialize(const cv::Mat& original);
    void push(const HistoryEntry& entry);
    bool canUndo() const;
    bool canRedo() const;
    bool jumpTo(int index);
    int currentIndex() const;
    int count() const;
    const HistoryEntry* entryAt(int index) const;
    const cv::Mat& currentImage() const;
private:
    QVector<HistoryEntry> m_entries;
    int m_currentIndex = -1;
    static constexpr int MAX_ENTRIES = 20;
};
```

### Behavior rules

1. `onLoadImage` success → `initialize(origImage)`, stack has 1 entry (original, index 0), pointer at 0.
2. `push` after successful Run: if current pointer is not at tail, discard entries after current (standard undo/redo semantics) then push.
3. Overflow: `count > MAX_ENTRIES` drops earliest entry (index 0), all indices shift. Original entry may be evicted; acceptable past 20 steps.
4. `undo`: `currentIndex--`, refresh viewer to `currentImage()`.
5. `redo`: `currentIndex++`.
6. `jumpTo`: UI lists history entries, click to jump.
7. `clear` on `onClear` or new image load.
8. Undo/redo do NOT push new entries — only Run pushes.

### Memory budget

B1 cap of 20. Assuming remote-sensing images ≤ 100 MB each, peak ≈ 2 GB
(20 × 100 MB). If real images are larger, tune `MAX_ENTRIES`.

### Relationship to presets

History stack = image snapshots of executed operations. Presets = named
parameter recipes. Orthogonal; no direct interaction. Applying a preset →
adjust params → Run → history pushes.

### ComparisonView data source

Always takes `HistoryStack.entryAt(0).image` (original) and
`HistoryStack.currentImage()` (current result) for comparison. Undo/redo
changes `currentImage`, viewer refreshes automatically.

## §5 — Slider Comparison View

### ComparisonView (QGraphicsView subclass)

```cpp
class ComparisonView : public QGraphicsView {
    Q_OBJECT
public:
    void setImages(const cv::Mat& original, const cv::Mat& result);
    void setSplitRatio(double ratio);   // 0.0=all-original, 1.0=all-result
    void fitToView();
signals:
    void cursorMoved(int px, int py);
protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void wheelEvent(QWheelEvent*) override;
private:
    QGraphicsPixmapItem* m_origItem;
    QGraphicsPixmapItem* m_resultItem;
    double m_splitRatio = 0.5;
    bool m_dragging = false;
};
```

### Render strategy (C1)

- Scene contains two `QGraphicsPixmapItem` at identical coordinates (overlapping).
- `m_resultItem` clipped via a `QPainterPath` rectangle: keeps right portion `>= splitRatio * width`, left portion shows `m_origItem`.
- On each `setSplitRatio`, rebuild clip path and emit `splitRatioChanged` to trigger repaint.
- Split line + handle drawn as `QGraphicsLineItem` + `QGraphicsRectItem` on top layer.

### Drag interaction

- Mouse press within ±6 px of the split line → enter drag mode.
- `mouseMove` → `setSplitRatio = (mouseX - viewLeft) / viewWidth`.
- `setSplitRatio` emits signal → repaint.

### Zoom / pan

Reuses `RasterViewerWidget`'s wheel/pan logic (extract to a shared base or mixin).
Single viewer → two pixmaps zoom together → inherent zoom sync. Q6 "zoom sync"
is automatically satisfied in comparison mode.

### Non-comparison mode

When comparison is off, `ComparisonView` enters single-image mode showing only
the result image (the original pixmap is hidden, the split line is not drawn).
`setSplitRatio` is irrelevant in this mode. This replaces the existing
`m_resultViewer`; `m_origViewer` is retained for standalone original viewing.

Note: `splitRatio` semantics (`0.0 = all original, 1.0 = all result`) apply only
in compare mode. In single-image mode the original pixmap is hidden entirely
so the ratio has no visible effect.

### Integration with right panel

Right panel changes from "orig viewer + result viewer split" to "orig viewer
(small, collapsible) + ComparisonView (large, default shows result, shows
slider when comparison enabled)". Splitter layout; orig viewer foldable.

## §6 — Preset Management

### PresetManager (thin wrapper over ProjectModel)

```cpp
struct Preset {
    QString name;
    QString opId;
    rstao::ParamMap params;
};

class PresetManager {
public:
    explicit PresetManager(ProjectModel* project);
    QList<Preset> presetsForOperator(const QString& opId) const;
    QList<Preset> allPresets() const;
    void savePreset(const Preset& preset);     // same name overwrites
    bool deletePreset(const QString& opId, const QString& name);
private:
    ProjectModel* m_project;
    QJsonArray presetsArray() const;
    void writePresetsArray(const QJsonArray& arr);
};
```

### ProjectModel extension (schema 4 → 5)

- New top-level key `image_processing_presets: [...]`.
- `loadProject` ensures default key (same pattern as existing `resources`).
- Migration: on load if `schema_version < 5`, set `image_processing_presets = []`; bump to 5 on save.
- `SCHEMA_VERSION` 4 → 5.

### Preset JSON structure

```json
{
  "image_processing_presets": [
    {"name": "Gaussian-Soft", "opId": "smooth", "params": {"method": "gaussian", "ksize": 5}},
    {"name": "Sharpen-Strong", "opId": "sharpen", "params": {"method": "unsharp_mask", "amount": 2.0}}
  ]
}
```

### UI interaction

- Parameter card gains a "Preset" row at the bottom: dropdown (presets for current operator) + Save + Delete + Apply buttons.
- "Save": collect current params → input dialog for name → `savePreset` → `ProjectModel::saveProject()` flushes to disk.
- "Apply": read params from selected preset → populate param widgets.
- Switching operator refreshes the preset dropdown.
- When no project is open: preset area disabled with hint "create/open a project first" (Tab holds `ProjectModel*`; `isOpen()` false disables).

### Relationship to history

Presets = parameter recipes; history = image snapshots. Applying a preset →
adjust → Run → history push. No direct interaction.

## §7 — Batch Processing

### Batch panel (collapsible widget below the left panel)

| Element | Description |
|---------|-------------|
| Input folder | `QLineEdit` + Browse button |
| Output folder | `QLineEdit` + Browse button; default = input + `_out` suffix |
| Output format | `QComboBox`: PNG / JPEG / TIFF |
| Operator chain | `OperatorChainWidget`: add/remove rows, each row = operator dropdown + params edit button |
| Progress | `QProgressBar` + current filename label + "X / N" count |
| Start/Cancel | Single reused button (same Run/Cancel pattern as single-image) |
| Log | `QTextEdit` read-only, records success/fail/skip |

### OperatorChainWidget

```cpp
struct ChainStep {
    QString opId;
    rstao::ParamMap params;
};

class OperatorChainWidget : public QWidget {
    Q_OBJECT
public:
    QVector<ChainStep> chain() const;
    void setChain(const QVector<ChainStep>& steps);
signals:
    void changed();
private slots:
    void addStep();
    void removeStep();
    void editStep();
private:
    QTableWidget* m_table;   // columns: operator display name, params summary, actions
};
```

- Each row shows operator i18n name + params summary (e.g. `ksize=5, method=gaussian`).
- "Edit params" opens a `QDialog` reusing the existing `buildParameterWidgets` logic.
- Row drag reorder via `QTableWidget::setDragEnabled` + `internalMove`.

### BatchRequest and execution

```cpp
struct BatchRequest {
    QStringList inputFiles;
    QString outputDir;
    QVector<ChainStep> chain;
    QString outputFormat;   // "png"|"jpg"|"tif"
};
```

- Scan input folder: `QDir::entryList` filtering image extensions (`.png/.jpg/.jpeg/.tif/.tiff/.bmp`).
- Per file: `read_image` → for each chain step `process(src, step.opId, step.params, progressCb)` → `save_image(outDir/<base>_proc.<ext>)`.
  - Output naming: `<basename>_proc.<ext>` (chain result; intermediate steps not written).
  - Single-step chain also uses `<basename>_proc.<ext>`.
- Failure handling: single-image failure is logged; batch continues.
- On completion no modal dialog; log shows "done: N succeeded, M failed".

### State machine integration

Batch running → tab enters `BatchRunning`; single-image Run disabled; batch
button becomes "Cancel". On cancel, completed files remain.

### Relationship to single-image async

Reuses `rstao::ProgressCallback`, but `BatchWorker` is an independent class
(not shared with `ProcessingWorker`) because progress semantics differ
(file-level vs in-image-level).

## §8 — Drag-drop and Integration Layout

### Drag-drop

- `ImageProcessingTab::dragEnterEvent`: accept if mimeData has urls with image extensions.
- `ImageProcessingTab::dropEvent`: take first url → reuse `onLoadImage` internal logic (path → `read_image` → `HistoryStack.initialize` → refresh viewer).
- Whole tab is drop target (left panel or comparison area).
- Multi-file drop: use first, ignore rest (batch uses folder picker, not drag).

### Tab holds ProjectModel

- `ImageProcessingTab` constructor gains `ProjectModel*` parameter (default nullptr).
- `MainWindow::buildUi()` passes `&m_projectModel` when constructing the tab.
- If nullptr (legacy callers): presets disabled, rest works.

### Right panel layout

```
splitter (horizontal)
├── orig viewer (collapsible, default 30% width)
└── ComparisonView (default 70% width)
    ├── single mode: result only (original pixmap hidden)
    └── compare mode: slider comparison (splitRatio=0.5, 0.0=all-orig, 1.0=all-result)
```

- Top of right panel: `QCheckBox` "Compare mode" → toggles ComparisonView compare/single.
- orig viewer retained for standalone original viewing; in compare mode it can be hidden (folded into splitter).

### Left panel additions

- Parameter card gains a "Preset" row (§6).
- Bottom gains a collapsible "Batch" section (§7), collapsed by default; expand to reveal `OperatorChainWidget`.

### Undo / Redo buttons

- Action card adds `Undo` + `Redo` buttons, enabled by `canUndo`/`canRedo`.
- "History" button opens `QDialog` listing all stack entries; click to jumpTo.

### Button state table (`updateButtonStates()`)

| State | Run | Cancel | Undo | Redo | Save preset | Apply preset | Batch | Save |
|-------|-----|--------|------|------|-------------|--------------|-------|------|
| Idle | ✓ (has image + operator) | — | canUndo | canRedo | isOpen | isOpen+has preset | ✓ | has result |
| SingleRunning | →Cancel | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| BatchRunning | ✗ | ✓ (batch) | ✗ | ✗ | ✗ | ✗ | →Cancel | ✗ |

## Testing Considerations

- `HistoryStack`: unit test push/undo/redo/jump/cap behavior (can be a Qt-independent
  class if `HistoryEntry` is plain data).
- `PresetManager`: unit test save/load/delete against an in-memory `ProjectModel`.
- rstao_core: new `ProgressCallback` overload covered in existing test binaries;
  add cancel-throw test.
- UI behavior (drag-drop, comparison slider, batch): manual verification via
  `run.bat Release` — launch, load image, run operators, undo/redo, save preset,
  run batch on a folder, compare slider.
- Existing 3 GTest binaries remain green; `build_all.bat Release` must succeed.

## Out of Scope

- True Debug CRT builds (still using Release CRT workaround).
- Persistent history stack (history is in-memory only; not saved to project file).
- Batch processing of mixed operator chains saved as a "chain preset" (chain is
  configured per-run; saving chains as named entities is a future enhancement).
- Real-time / live preview (operators run on Run click, not on parameter change).

## File Impact Summary

| File | Action |
|------|--------|
| `cpp/include/rstao/image_processing.hpp` | Add `ProgressCallback`, new `process` overload, `OperationCanceled` |
| `cpp/src/image_processing.cpp` | Implement progress milestones per operator; new overload |
| `cpp/tests/test_image_processing.cpp` | Add progress + cancel tests |
| `cpp_qt/src/tabs/ImageProcessingTab.h` | Add ProjectModel*, workers, history, comparison, preset, chain members |
| `cpp_qt/src/tabs/ImageProcessingTab.cpp` | State machine, wiring, drag-drop, button states |
| `cpp_qt/src/widgets/ComparisonView.h/.cpp` | New — slider comparison view |
| `cpp_qt/src/widgets/RasterViewerWidget.h/.cpp` | Extract shared zoom/pan mixin for ComparisonView reuse |
| `cpp_qt/src/core/ProcessingWorker.h/.cpp` | New — single-image async worker |
| `cpp_qt/src/core/BatchWorker.h/.cpp` | New — batch worker |
| `cpp_qt/src/core/HistoryStack.h/.cpp` | New — undo/redo stack |
| `cpp_qt/src/core/PresetManager.h/.cpp` | New — preset façade |
| `cpp_qt/src/widgets/OperatorChainWidget.h/.cpp` | New — batch chain editor |
| `cpp_qt/src/ProjectModel.h/.cpp` | `SCHEMA_VERSION` 4→5; preset key accessors |
| `cpp_qt/src/MainWindow.cpp` | Pass `&m_projectModel` to ImageProcessingTab |
| `cpp_qt/CMakeLists.txt` | Add new source files |
| `cpp_qt/src/I18n.cpp` (or equivalent) | New i18n keys for undo/redo/preset/batch/compare |
