# ImageProcessingTab UI Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade ImageProcessingTab from synchronous single-image demo into async, undoable, preset-driven, comparison-aware workspace with batch processing.

**Architecture:** Add `ProcessingWorker`/`BatchWorker` (QThread-based async execution with progress signals), `HistoryStack` (LRU-20 in-memory undo/redo), `ComparisonView` (single QGraphicsView + dual pixmap + draggable split), `PresetManager` (ProjectModel-backed named parameter recipes), `OperatorChainWidget` (batch chain editor). Extend rstao_core with `ProgressCallback` + new `process()` overload. Rewrite ImageProcessingTab to orchestrate all components via an idle/singleRunning/batchRunning state machine.

**Tech Stack:** C++17, Qt6 6.9.3, OpenCV 4.12.0, GTest, MSVC 19.44, CMake 3.16+

## Global Constraints

- C++ standard: C++17 (`CMAKE_CXX_STANDARD 17`)
- CRT: `CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL"` + `_ITERATOR_DEBUG_LEVEL=0` in Debug — MUST be preserved
- rstao_core Debug lib maps to Release lib in cpp_qt/CMakeLists.txt — MUST be preserved
- conda environment name: `RSTao_tool`
- CMake generator: "Visual Studio 18 2026" -A x64
- All .cpp/.h files use UTF-8 (`/utf-8` compile flag)
- No absolute hardcoded paths
- cpp/ has zero Qt dependency; cpp_qt/ contains all Qt code
- Existing signatures preserved — `process(src, opId, params)` must keep working

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `cpp/include/rstao/image_processing.hpp` | Modify | Add `ProgressCallback`, `OperationCanceled`, new `process` overload |
| `cpp/src/image_processing.cpp` | Modify | Implement per-operator progress milestones, cancel checks, new overload |
| `cpp/tests/test_image_processing.cpp` | Modify | Add progress callback + cancel tests |
| `cpp_qt/src/core/ProgressableWorker.h` | Create | Abstract base: QObject + QThread management + cancel |
| `cpp_qt/src/core/ProcessingWorker.h` | Create | Single-image async worker declaration |
| `cpp_qt/src/core/ProcessingWorker.cpp` | Create | Single-image async worker implementation |
| `cpp_qt/src/core/BatchWorker.h` | Create | Batch worker declaration |
| `cpp_qt/src/core/BatchWorker.cpp` | Create | Batch worker implementation |
| `cpp_qt/src/core/HistoryStack.h` | Create | Undo/redo stack declaration |
| `cpp_qt/src/core/HistoryStack.cpp` | Create | Undo/redo stack implementation |
| `cpp_qt/src/core/PresetManager.h` | Create | Preset façade declaration |
| `cpp_qt/src/core/PresetManager.cpp` | Create | Preset façade implementation |
| `cpp_qt/src/widgets/OperatorChainWidget.h` | Create | Batch chain editor declaration |
| `cpp_qt/src/widgets/OperatorChainWidget.cpp` | Create | Batch chain editor implementation |
| `cpp_qt/src/widgets/ComparisonView.h` | Create | Slider comparison view declaration |
| `cpp_qt/src/widgets/ComparisonView.cpp` | Create | Slider comparison view implementation |
| `cpp_qt/src/tabs/ImageProcessingTab.h` | Modify | Add new members, state machine, drag-drop overrides |
| `cpp_qt/src/tabs/ImageProcessingTab.cpp` | Modify | Full rewrite: state machine, wiring, new UI |
| `cpp_qt/src/ProjectModel.h` | Modify | `SCHEMA_VERSION` 4→5, preset accessors |
| `cpp_qt/src/ProjectModel.cpp` | Modify | Schema migration, preset read/write |
| `cpp_qt/src/I18n.cpp` | Modify | New i18n keys for undo/redo/preset/batch/compare |
| `cpp_qt/src/MainWindow.cpp` | Modify | Pass `&m_projectModel` to ImageProcessingTab |
| `cpp_qt/CMakeLists.txt` | Modify | Add new source files |

---

### Task 1: rstao_core — ProgressCallback and Cancel Base

**Files:**
- Modify: `cpp/include/rstao/image_processing.hpp:1-45`
- Modify: `cpp/src/image_processing.cpp:466-523` (the `process` dispatch function)

**Interfaces:**
- Produces: `rstao::ProgressCallback` (using alias), `rstao::OperationCanceled` (exception), `rstao::process(src, opId, params, progress)` (new overload)

- [ ] **Step 1: Add ProgressCallback and OperationCanceled to header**

In `migration_project/cpp/include/rstao/image_processing.hpp`, after the `#include` block and before the operator declarations, add:

```cpp
#include <functional>
#include <stdexcept>

namespace rstao {

using ProgressCallback = std::function<void(int /*percent 0-100*/)>;

class OperationCanceled : public std::runtime_error {
public:
    OperationCanceled() : std::runtime_error("Operation was canceled") {}
};

// ... existing declarations stay below ...
```

- [ ] **Step 2: Add new process overload declaration to header**

After line 43 (`ProcessingResult process(...`), add:

```cpp
// With progress callback — worker thread calls progress(percent) during execution.
ProcessingResult process(const Image& image, const std::string& op_id,
                         const ParamMap& params, ProgressCallback progress);
```

- [ ] **Step 3: Implement the new process overload**

Replace the body of `process` (lines 466-523) with a two-function pattern: extract the existing dispatch into a private helper, then call it from both overloads. The new overload passes the callback through.

In `migration_project/cpp/src/image_processing.cpp`, replace lines 466-523:

```cpp
namespace {

// Forward callback helper through a per-operator call.
// When progress is null, operators skip progress reporting (existing behavior).
Image dispatchProcess(const Image& image, const std::string& opId,
                      const ParamMap& params, ProgressCallback progress) {
    auto callProgress = [&](int p) { if (progress) progress(p); };
    callProgress(0);
    Image result;

    if (opId == "grayscale") {
        callProgress(50);
        result = to_grayscale(image);
        callProgress(100);
    } else if (opId == "color_space") {
        callProgress(30);
        result = convert_color_space(image, paramStr(params, "target", "HSV"));
        callProgress(100);
    } else if (opId == "linear_stretch") {
        callProgress(25);
        result = linear_stretch(image, paramDouble(params, "low_percent", 2.0),
                                         paramDouble(params, "high_percent", 98.0));
        callProgress(100);
    } else if (opId == "histogram_equalization") {
        callProgress(50);
        result = histogram_equalize(image);
        callProgress(100);
    } else if (opId == "histogram_match") {
        throw std::invalid_argument("histogram_match requires reference image, use match_histogram() directly");
    } else if (opId == "smooth") {
        callProgress(30);
        result = smooth(image, paramStr(params, "method", "gaussian"),
                                paramInt(params, "ksize", 5));
        callProgress(100);
    } else if (opId == "sharpen") {
        callProgress(30);
        result = sharpen(image, paramStr(params, "method", "unsharp_mask"),
                                  paramDouble(params, "amount", 1.0));
        callProgress(100);
    } else if (opId == "edge_detect") {
        callProgress(25);
        result = edge_detect(image, paramStr(params, "mode", "magnitude"));
        callProgress(100);
    } else if (opId == "morphology") {
        callProgress(30);
        result = morphology(image, paramStr(params, "operation", "erode"),
                                     paramInt(params, "ksize", 3),
                                     paramInt(params, "iterations", 1));
        callProgress(100);
    } else if (opId == "threshold") {
        callProgress(30);
        result = threshold_binary(image, paramStr(params, "method", "otsu"),
                                           paramDouble(params, "threshold", 127),
                                           paramInt(params, "block_size", 11));
        callProgress(100);
    } else if (opId == "pca") {
        callProgress(50);
        result = pca_component(image, paramInt(params, "component", 1) - 1);
        callProgress(100);
    } else if (opId == "ihs_intensity") {
        callProgress(50);
        result = ihs_intensity(image);
        callProgress(100);
    } else if (opId == "fft_filter") {
        callProgress(40);
        result = fft_filter(image, paramStr(params, "mode", "lowpass"),
                                     paramDouble(params, "radius", 30.0));
        callProgress(70);
        callProgress(100);
    } else if (opId == "normalized_difference") {
        callProgress(50);
        result = normalized_difference(image, paramInt(params, "band_a", 1) - 1,
                                                paramInt(params, "band_b", 2) - 1);
        callProgress(100);
    } else {
        throw std::invalid_argument("Unknown operator: " + opId);
    }
    return result;
}

} // anonymous namespace

ProcessingResult process(const Image& image, const std::string& opId, const ParamMap& params) {
    if (image.empty())
        throw std::invalid_argument("Input image is empty");

    Image result = dispatchProcess(image, opId, params, nullptr);

    Metrics metrics = basicMetrics(result);
    metrics["operator_id"] = opId;
    return ProcessingResult{result, metrics, Image()};
}

ProcessingResult process(const Image& image, const std::string& opId,
                         const ParamMap& params, ProgressCallback progress) {
    if (image.empty())
        throw std::invalid_argument("Input image is empty");

    Image result = dispatchProcess(image, opId, params, progress);

    Metrics metrics = basicMetrics(result);
    metrics["operator_id"] = opId;
    return ProcessingResult{result, metrics, Image()};
}
```

Note: the `dispatchProcess` and the two `process` overloads replace the existing single `process` function body. The anonymous namespace helper avoids duplicating the if-else chain.

- [ ] **Step 4: Build rstao_core to verify compilation**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release
```
Expected: compiles without errors.

- [ ] **Step 5: Run existing tests to confirm no regression**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp\build
ctest --output-on-failure -C Release
```
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/include/rstao/image_processing.hpp migration_project/cpp/src/image_processing.cpp
git commit -m "feat: add ProgressCallback and cancel support to rstao_core process

- New rstao::ProgressCallback = std::function<void(int)>
- New rstao::OperationCanceled exception
- New process() overload accepting ProgressCallback
- Per-operator progress milestones (see design spec §2)
- Existing signature preserved — no regression"
```

---

### Task 2: rstao_core — Progress and Cancel Tests

**Files:**
- Modify: `cpp/tests/test_image_processing.cpp`

**Interfaces:**
- Consumes: `rstao::process(src, opId, params, progress)` (from Task 1)
- Produces: GTest coverage for progress milestone counting and cancel-path verification

- [ ] **Step 1: Append progress and cancel tests**

In `migration_project/cpp/tests/test_image_processing.cpp`, append before the last line:

```cpp
// ---- Progress callback tests ----

TEST(ProgressCallback, ReceivesMilestones) {
    cv::Mat src = makeColorImage();
    std::vector<int> milestones;
    auto cb = [&](int p) { milestones.push_back(p); };

    ProcessingResult result = process(src, "grayscale", {}, cb);
    EXPECT_FALSE(result.image.empty());
    ASSERT_GE(milestones.size(), 2u);
    EXPECT_EQ(milestones.front(), 0);   // starts at 0
    EXPECT_EQ(milestones.back(), 100);  // ends at 100
}

TEST(ProgressCallback, PassesForAllOperators) {
    cv::Mat src = makeColorImage();
    std::vector<std::string> opIds = {
        "grayscale", "color_space", "linear_stretch", "histogram_equalization",
        "smooth", "sharpen", "edge_detect", "morphology", "threshold",
        "pca", "ihs_intensity", "fft_filter", "normalized_difference"
    };
    for (const auto& opId : opIds) {
        int finalPct = 0;
        auto cb = [&](int p) { finalPct = p; };
        ProcessingResult result = process(src, opId, {}, cb);
        EXPECT_FALSE(result.image.empty()) << "Operator: " << opId;
        EXPECT_EQ(finalPct, 100) << "Operator: " << opId;
    }
}

TEST(ProgressCallback, ParametrizedOperatorReceivesProgress) {
    cv::Mat src = makeColorImage();
    int lastPct = -1;
    auto cb = [&](int p) { lastPct = p; };
    ParamMap params;
    params["method"] = std::string("gaussian");
    params["ksize"] = 5;
    ProcessingResult result = process(src, "smooth", params, cb);
    EXPECT_FALSE(result.image.empty());
    EXPECT_EQ(lastPct, 100);
}

TEST(ProgressCallback, ExistingOverloadStillWorks) {
    cv::Mat src = makeColorImage();
    // Call the old overload (no callback) — must not crash or throw
    ProcessingResult result = process(src, "grayscale");
    EXPECT_FALSE(result.image.empty());
}

// ---- Cancel tests ----

TEST(Cancel, ThrowsOperationCanceled) {
    cv::Mat src = makeColorImage();
    auto cb = [&](int) -> void {
        throw OperationCanceled();
    };
    EXPECT_THROW(process(src, "grayscale", {}, cb), OperationCanceled);
}
```

- [ ] **Step 2: Build and run tests**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release
cd build
ctest --output-on-failure -C Release
```
Expected: all tests pass (existing + 6 new).

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/tests/test_image_processing.cpp
git commit -m "test: add progress callback and cancel tests for rstao_core

- Progress milestones: starts at 0, ends at 100, for all 13 operators
- Cancel: OperationCanceled thrown from callback propagates correctly
- Old overload still works without callback"
```

---

### Task 3: ProgressableWorker — Abstract Async Base

**Files:**
- Create: `cpp_qt/src/core/ProgressableWorker.h`
- Create: `cpp_qt/src/core/ProgressableWorker.cpp`

**Interfaces:**
- Produces: `ProgressableWorker` (QObject with QThread management, cancel, and progress signals)
- Consumed by: Task 4 (ProcessingWorker), Task 5 (BatchWorker)

- [ ] **Step 1: Create ProgressableWorker.h**

Create `migration_project/cpp_qt/src/core/ProgressableWorker.h`:

```cpp
#pragma once

#include <QObject>
#include <QThread>
#include <atomic>
#include <functional>

class ProgressableWorker : public QObject {
    Q_OBJECT
public:
    explicit ProgressableWorker(QObject* parent = nullptr);
    ~ProgressableWorker() override;

    void cancel();
    bool isCanceled() const;
    bool isRunning() const;

signals:
    void progress(int percent);
    void finished();
    void failed(QString message);
    void canceled();
    void started();

protected:
    void startWork(std::function<void()> work);
    QThread* workerThread() const;

private:
    QThread* m_thread;
    std::atomic<bool> m_canceled{false};
    std::atomic<bool> m_running{false};
};
```

- [ ] **Step 2: Create ProgressableWorker.cpp**

Create `migration_project/cpp_qt/src/core/ProgressableWorker.cpp`:

```cpp
#include "ProgressableWorker.h"
#include <QApplication>

ProgressableWorker::ProgressableWorker(QObject* parent)
    : QObject(parent)
    , m_thread(new QThread(this))
{
    m_thread->setObjectName("WorkerThread");
}

ProgressableWorker::~ProgressableWorker() {
    cancel();
    if (m_thread->isRunning()) {
        m_thread->quit();
        m_thread->wait(3000);
    }
}

void ProgressableWorker::cancel() {
    m_canceled.store(true, std::memory_order_release);
}

bool ProgressableWorker::isCanceled() const {
    return m_canceled.load(std::memory_order_acquire);
}

bool ProgressableWorker::isRunning() const {
    return m_running.load(std::memory_order_acquire);
}

void ProgressableWorker::startWork(std::function<void()> work) {
    m_canceled.store(false, std::memory_order_release);
    m_running.store(true, std::memory_order_release);

    auto* wrapper = new QObject();
    wrapper->moveToThread(m_thread);

    connect(m_thread, &QThread::started, wrapper, [=]() {
        try {
            work();
            if (!isCanceled()) {
                QMetaObject::invokeMethod(this, [this]() {
                    m_running.store(false, std::memory_order_release);
                    emit finished();
                }, Qt::QueuedConnection);
            }
        } catch (const std::exception& e) {
            QString msg = QString::fromStdString(e.what());
            QMetaObject::invokeMethod(this, [this, msg]() {
                m_running.store(false, std::memory_order_release);
                emit failed(msg);
            }, Qt::QueuedConnection);
        } catch (...) {
            QMetaObject::invokeMethod(this, [this]() {
                m_running.store(false, std::memory_order_release);
                emit failed(QStringLiteral("Unknown error"));
            }, Qt::QueuedConnection);
        }
    });

    connect(m_thread, &QThread::finished, wrapper, &QObject::deleteLater);
    m_thread->start();
    emit started();
}

QThread* ProgressableWorker::workerThread() const {
    return m_thread;
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/core/ProgressableWorker.h migration_project/cpp_qt/src/core/ProgressableWorker.cpp
git commit -m "feat: add ProgressableWorker base class for async Qt operations

- Manages QThread lifecycle + cancel flag
- startWork() runs std::function in worker thread
- Emits started/finished/failed/canceled/progress signals"
```

---

### Task 4: ProcessingWorker — Single-Image Async

**Files:**
- Create: `cpp_qt/src/core/ProcessingWorker.h`
- Create: `cpp_qt/src/core/ProcessingWorker.cpp`

**Interfaces:**
- Consumes: `ProgressableWorker` (Task 3), `rstao::process(src, opId, params, progress)` (Task 1)
- Produces: `ProcessingWorker` — `run(src, opId, params)` → emits `finished(result, opId, params)`
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Create ProcessingWorker.h**

Create `migration_project/cpp_qt/src/core/ProcessingWorker.h`:

```cpp
#pragma once

#include "ProgressableWorker.h"
#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

class ProcessingWorker : public ProgressableWorker {
    Q_OBJECT
public:
    explicit ProcessingWorker(QObject* parent = nullptr);

    void run(const cv::Mat& src, const QString& opId, const rstao::ParamMap& params);

signals:
    void finished(rstao::ProcessingResult result, QString opId, rstao::ParamMap params);
    void canceled();

private:
    cv::Mat m_inputCopy;
    QString m_opId;
    rstao::ParamMap m_params;
};
```

- [ ] **Step 2: Create ProcessingWorker.cpp**

Create `migration_project/cpp_qt/src/core/ProcessingWorker.cpp`:

```cpp
#include "ProcessingWorker.h"
#include <rstao/image_processing.hpp>

ProcessingWorker::ProcessingWorker(QObject* parent)
    : ProgressableWorker(parent)
{
}

void ProcessingWorker::run(const cv::Mat& src, const QString& opId, const rstao::ParamMap& params) {
    if (isRunning()) return;

    m_inputCopy = src.clone();
    m_opId = opId;
    m_params = params;
    std::string opIdStr = opId.toStdString();

    startWork([this, opIdStr]() {
        rstao::ProgressCallback cb = [this](int pct) {
            if (isCanceled()) throw rstao::OperationCanceled();
            QMetaObject::invokeMethod(this, [this, pct]() {
                emit progress(pct);
            }, Qt::QueuedConnection);
        };

        try {
            rstao::ProcessingResult r = rstao::process(m_inputCopy, opIdStr, m_params, cb);
            QMetaObject::invokeMethod(this, [this, r, opId = m_opId, params = m_params]() mutable {
                emit finished(std::move(r), opId, params);
            }, Qt::QueuedConnection);
        } catch (const rstao::OperationCanceled&) {
            QMetaObject::invokeMethod(this, [this]() {
                emit canceled();
            }, Qt::QueuedConnection);
        }
    });
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/core/ProcessingWorker.h migration_project/cpp_qt/src/core/ProcessingWorker.cpp
git commit -m "feat: add ProcessingWorker for async single-image processing

- Runs rstao::process in background QThread
- Emits progress/percent via queued signal
- Cancel propagates through ProgressCallback → OperationCanceled"
```

---

### Task 5: BatchWorker — Batch Async

**Files:**
- Create: `cpp_qt/src/core/BatchWorker.h`
- Create: `cpp_qt/src/core/BatchWorker.cpp`

**Interfaces:**
- Consumes: `ProgressableWorker` (Task 3), `rstao::process(src, opId, params, progress)` (Task 1)
- Produces: `BatchWorker` — `run(BatchRequest)` → emits `progress`, `fileFinished`, `batchFinished`
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Create BatchWorker.h**

Create `migration_project/cpp_qt/src/core/BatchWorker.h`:

```cpp
#pragma once

#include "ProgressableWorker.h"

#include <QString>
#include <QStringList>
#include <QVector>
#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

struct ChainStep {
    QString opId;
    rstao::ParamMap params;

    bool isValid() const { return !opId.isEmpty(); }
};

struct BatchRequest {
    QStringList inputFiles;
    QString outputDir;
    QVector<ChainStep> chain;
    QString outputFormat;  // "png", "jpg", "tif"
};

class BatchWorker : public ProgressableWorker {
    Q_OBJECT
public:
    explicit BatchWorker(QObject* parent = nullptr);

    void run(const BatchRequest& request);

signals:
    void fileFinished(const QString& path);
    void batchFinished(int succeeded, int failed);
    void canceled();

private:
    void processFile(const QString& path, const QVector<ChainStep>& chain,
                     const QString& outputDir, const QString& format,
                     int fileIndex, int totalFiles);
    static QString makeOutputPath(const QString& inputPath, const QString& outputDir,
                                  const QString& format);

    QStringList m_inputFiles;
    QVector<ChainStep> m_chain;
    QString m_outputDir;
    QString m_outputFormat;
    int m_succeeded = 0;
    int m_failed = 0;
};
```

- [ ] **Step 2: Create BatchWorker.cpp**

Create `migration_project/cpp_qt/src/core/BatchWorker.cpp`:

```cpp
#include "BatchWorker.h"
#include <rstao/image_processing.hpp>
#include <rstao/image_io.hpp>

#include <QDir>
#include <QFileInfo>

BatchWorker::BatchWorker(QObject* parent)
    : ProgressableWorker(parent)
{
}

void BatchWorker::run(const BatchRequest& request) {
    if (isRunning()) return;
    if (request.inputFiles.isEmpty() || request.chain.isEmpty()) return;

    m_inputFiles = request.inputFiles;
    m_chain = request.chain;
    m_outputDir = request.outputDir;
    m_outputFormat = request.outputFormat.isEmpty() ? QStringLiteral("png") : request.outputFormat;
    m_succeeded = 0;
    m_failed = 0;

    QDir().mkpath(m_outputDir);

    int total = m_inputFiles.size();

    startWork([this, total]() {
        for (int i = 0; i < m_inputFiles.size(); ++i) {
            if (isCanceled()) break;

            const QString& path = m_inputFiles[i];
            processFile(path, m_chain, m_outputDir, m_outputFormat, i, total);

            int overallPct = static_cast<int>((i + 1) * 100.0 / total);
            QMetaObject::invokeMethod(this, [this, overallPct]() {
                emit progress(overallPct);
            }, Qt::QueuedConnection);
        }

        int succ = m_succeeded;
        int fail = m_failed;
        QMetaObject::invokeMethod(this, [this, succ, fail]() {
            emit batchFinished(succ, fail);
        }, Qt::QueuedConnection);
    });
}

void BatchWorker::processFile(const QString& path, const QVector<ChainStep>& chain,
                               const QString& outputDir, const QString& format,
                               int fileIndex, int totalFiles)
{
    Q_UNUSED(fileIndex)
    Q_UNUSED(totalFiles)

    try {
        cv::Mat current = rstao::read_image(path.toStdString());
        if (current.empty()) {
            ++m_failed;
            emit fileFinished(path);
            return;
        }

        for (const auto& step : chain) {
            rstao::ProgressCallback cb = [this](int /*pct*/) {
                if (isCanceled()) throw rstao::OperationCanceled();
            };
            current = rstao::process(current, step.opId.toStdString(), step.params, cb).image;
        }

        QString outPath = makeOutputPath(path, outputDir, format);
        rstao::save_image(outPath.toStdString(), current);
        ++m_succeeded;
        emit fileFinished(path);
    } catch (const rstao::OperationCanceled&) {
        return;  // cancel flag will break the outer loop
    } catch (const std::exception&) {
        ++m_failed;
        emit fileFinished(path);
    }
}

QString BatchWorker::makeOutputPath(const QString& inputPath, const QString& outputDir,
                                     const QString& format)
{
    QFileInfo fi(inputPath);
    QString base = fi.completeBaseName();
    QString ext = format.startsWith('.') ? format.mid(1) : format;
    return outputDir + "/" + base + "_proc." + ext;
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/core/BatchWorker.h migration_project/cpp_qt/src/core/BatchWorker.cpp
git commit -m "feat: add BatchWorker for async batch processing

- Runs operator chain on all images in a folder
- Per-file progress + overall percentage
- Single file failure doesn't stop the batch
- Output to disk folder with _proc suffix"
```

---

### Task 6: HistoryStack — Undo/Redo

**Files:**
- Create: `cpp_qt/src/core/HistoryStack.h`
- Create: `cpp_qt/src/core/HistoryStack.cpp`

**Interfaces:**
- Produces: `HistoryStack` — `initialize(orig)`, `push(entry)`, `undo()`, `redo()`, `jumpTo(idx)`, `currentImage()`
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Create HistoryStack.h**

Create `migration_project/cpp_qt/src/core/HistoryStack.h`:

```cpp
#pragma once

#include <QString>
#include <QVector>
#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

struct HistoryEntry {
    cv::Mat image;
    QString opId;
    rstao::ParamMap params;
    QString description;
};

class HistoryStack {
public:
    HistoryStack();

    void initialize(const cv::Mat& original);
    void push(const HistoryEntry& entry);
    bool pushIfNew(const HistoryEntry& entry);  // returns true if actually pushed

    bool canUndo() const;
    bool canRedo() const;
    void undo();
    void redo();
    bool jumpTo(int index);

    int currentIndex() const;
    int count() const;
    const HistoryEntry* entryAt(int index) const;
    const cv::Mat& currentImage() const;
    void clear();

private:
    void evictOne();

    QVector<HistoryEntry> m_entries;
    int m_currentIndex = -1;
    static constexpr int MAX_ENTRIES = 20;
};
```

- [ ] **Step 2: Create HistoryStack.cpp**

Create `migration_project/cpp_qt/src/core/HistoryStack.cpp`:

```cpp
#include "HistoryStack.h"

HistoryStack::HistoryStack() = default;

void HistoryStack::initialize(const cv::Mat& original) {
    m_entries.clear();
    m_currentIndex = -1;
    HistoryEntry e;
    e.image = original.clone();
    e.opId = QStringLiteral("_original");
    e.description = QStringLiteral("Original");
    m_entries.append(e);
    m_currentIndex = 0;
}

void HistoryStack::push(const HistoryEntry& entry) {
    if (m_entries.isEmpty()) return;

    // Discard forward history if not at tip
    while (m_entries.size() > m_currentIndex + 1)
        m_entries.removeLast();

    m_entries.append(entry);

    while (m_entries.size() > MAX_ENTRIES)
        evictOne();

    m_currentIndex = m_entries.size() - 1;
}

bool HistoryStack::pushIfNew(const HistoryEntry& entry) {
    push(entry);
    return true;
}

bool HistoryStack::canUndo() const {
    return m_currentIndex > 0;
}

bool HistoryStack::canRedo() const {
    return m_currentIndex < m_entries.size() - 1;
}

void HistoryStack::undo() {
    if (canUndo()) --m_currentIndex;
}

void HistoryStack::redo() {
    if (canRedo()) ++m_currentIndex;
}

bool HistoryStack::jumpTo(int index) {
    if (index < 0 || index >= m_entries.size()) return false;
    m_currentIndex = index;
    return true;
}

int HistoryStack::currentIndex() const {
    return m_currentIndex;
}

int HistoryStack::count() const {
    return m_entries.size();
}

const HistoryEntry* HistoryStack::entryAt(int index) const {
    if (index < 0 || index >= m_entries.size()) return nullptr;
    return &m_entries.at(index);
}

const cv::Mat& HistoryStack::currentImage() const {
    if (m_currentIndex < 0 || m_currentIndex >= m_entries.size()) {
        static cv::Mat empty;
        return empty;
    }
    return m_entries.at(m_currentIndex).image;
}

void HistoryStack::clear() {
    m_entries.clear();
    m_currentIndex = -1;
}

void HistoryStack::evictOne() {
    if (m_entries.isEmpty()) return;
    m_entries.removeFirst();
    if (m_currentIndex > 0) --m_currentIndex;
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/core/HistoryStack.h migration_project/cpp_qt/src/core/HistoryStack.cpp
git commit -m "feat: add HistoryStack for multi-step undo/redo

- LRU cap of 20 in-memory cv::Mat snapshots
- Standard undo/redo: push after undo discards forward history
- jumpTo for arbitrary step access
- Overflow evicts oldest entry"
```

---

### Task 7: PresetManager + ProjectModel Schema 4→5

**Files:**
- Create: `cpp_qt/src/core/PresetManager.h`
- Create: `cpp_qt/src/core/PresetManager.cpp`
- Modify: `cpp_qt/src/ProjectModel.h:35` (SCHEMA_VERSION)
- Modify: `cpp_qt/src/ProjectModel.cpp` (migration + preset accessors)

**Interfaces:**
- Consumes: `ProjectModel` (existing)
- Produces: `PresetManager(ProjectModel*)` — `presetsForOperator(opId)`, `savePreset(Preset)`, `deletePreset(opId, name)`
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Bump SCHEMA_VERSION and add preset accessors to ProjectModel.h**

In `migration_project/cpp_qt/src/ProjectModel.h`, change line 35:

```cpp
static const int SCHEMA_VERSION = 5;
```

After `addDataSource` declaration (line 31), add:

```cpp
    // Presets (schema v5)
    QJsonArray presets() const;
    void setPresets(const QJsonArray& arr);
```

- [ ] **Step 2: Add migration and preset methods to ProjectModel.cpp**

In `migration_project/cpp_qt/src/ProjectModel.cpp`, in `loadProject`, after the existing `data_sources` guard block (line 47), add:

```cpp
    if (!m_project.contains("image_processing_presets"))
        m_project["image_processing_presets"] = QJsonArray();
```

After `addDataSource` (line 127), add:

```cpp
QJsonArray ProjectModel::presets() const {
    return m_project.value("image_processing_presets").toArray();
}

void ProjectModel::setPresets(const QJsonArray& arr) {
    m_project["image_processing_presets"] = arr;
}
```

- [ ] **Step 3: Create PresetManager.h**

Create `migration_project/cpp_qt/src/core/PresetManager.h`:

```cpp
#pragma once

#include <QString>
#include <QList>
#include <QJsonArray>
#include <rstao/common/types.hpp>

class ProjectModel;

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

    bool isAvailable() const;   // false when project is null or not open

private:
    QJsonArray presetsArray() const;
    void writePresetsArray(const QJsonArray& arr);
    static Preset fromJson(const QJsonObject& obj);
    static QJsonObject toJson(const Preset& p);

    ProjectModel* m_project;
};
```

- [ ] **Step 4: Create PresetManager.cpp**

Create `migration_project/cpp_qt/src/core/PresetManager.cpp`:

```cpp
#include "PresetManager.h"
#include "../ProjectModel.h"

#include <QJsonObject>
#include <QJsonDocument>

PresetManager::PresetManager(ProjectModel* project)
    : m_project(project)
{
}

bool PresetManager::isAvailable() const {
    return m_project && m_project->isOpen();
}

QList<Preset> PresetManager::presetsForOperator(const QString& opId) const {
    QList<Preset> result;
    for (const auto& v : presetsArray()) {
        QJsonObject obj = v.toObject();
        if (obj.value("opId").toString() == opId)
            result.append(fromJson(obj));
    }
    return result;
}

QList<Preset> PresetManager::allPresets() const {
    QList<Preset> result;
    for (const auto& v : presetsArray()) {
        result.append(fromJson(v.toObject()));
    }
    return result;
}

void PresetManager::savePreset(const Preset& preset) {
    QJsonArray arr = presetsArray();

    // Overwrite if same opId + name exists
    for (int i = 0; i < arr.size(); ++i) {
        QJsonObject obj = arr[i].toObject();
        if (obj.value("opId").toString() == preset.opId &&
            obj.value("name").toString() == preset.name) {
            arr[i] = toJson(preset);
            writePresetsArray(arr);
            return;
        }
    }
    arr.append(toJson(preset));
    writePresetsArray(arr);
}

bool PresetManager::deletePreset(const QString& opId, const QString& name) {
    QJsonArray arr = presetsArray();
    for (int i = 0; i < arr.size(); ++i) {
        QJsonObject obj = arr[i].toObject();
        if (obj.value("opId").toString() == opId &&
            obj.value("name").toString() == name) {
            arr.removeAt(i);
            writePresetsArray(arr);
            return true;
        }
    }
    return false;
}

QJsonArray PresetManager::presetsArray() const {
    if (!m_project) return QJsonArray();
    return m_project->presets();
}

void PresetManager::writePresetsArray(const QJsonArray& arr) {
    if (!m_project) return;
    m_project->setPresets(arr);
    m_project->saveProject();
}

Preset PresetManager::fromJson(const QJsonObject& obj) {
    Preset p;
    p.name = obj.value("name").toString();
    p.opId = obj.value("opId").toString();

    QJsonObject paramsObj = obj.value("params").toObject();
    for (auto it = paramsObj.constBegin(); it != paramsObj.constEnd(); ++it) {
        QJsonValue v = it.value();
        std::string key = it.key().toStdString();
        if (v.isDouble()) {
            // Heuristic: if the value is an integer-looking double, store as int
            double d = v.toDouble();
            if (d == static_cast<int>(d))
                p.params[key] = static_cast<int>(d);
            else
                p.params[key] = d;
        } else if (v.isBool()) {
            p.params[key] = v.toBool();
        } else if (v.isString()) {
            p.params[key] = v.toString().toStdString();
        }
    }
    return p;
}

QJsonObject PresetManager::toJson(const Preset& p) {
    QJsonObject obj;
    obj["name"] = p.name;
    obj["opId"] = p.opId;

    QJsonObject paramsObj;
    for (const auto& kv : p.params) {
        QString key = QString::fromStdString(kv.first);
        std::visit([&](const auto& val) {
            using T = std::decay_t<decltype(val)>;
            if constexpr (std::is_same_v<T, int>)
                paramsObj[key] = val;
            else if constexpr (std::is_same_v<T, double>)
                paramsObj[key] = val;
            else if constexpr (std::is_same_v<T, std::string>)
                paramsObj[key] = QString::fromStdString(val);
            else if constexpr (std::is_same_v<T, bool>)
                paramsObj[key] = val;
        }, kv.second);
    }
    obj["params"] = paramsObj;
    return obj;
}
```

- [ ] **Step 5: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/core/PresetManager.h migration_project/cpp_qt/src/core/PresetManager.cpp migration_project/cpp_qt/src/ProjectModel.h migration_project/cpp_qt/src/ProjectModel.cpp
git commit -m "feat: add PresetManager and bump ProjectModel schema to v5

- PresetManager wraps ProjectModel for named operator parameter recipes
- Schema migration: v4→v5 adds image_processing_presets key
- Presets grouped by operator, save/delete by name+opId
- ParamMap → JSON bidirectional conversion with int/double/string/bool"
```

---

### Task 8: ComparisonView — Slider Comparison

**Files:**
- Create: `cpp_qt/src/widgets/ComparisonView.h`
- Create: `cpp_qt/src/widgets/ComparisonView.cpp`

**Interfaces:**
- Consumes: `QGraphicsView` (Qt6)
- Produces: `ComparisonView` — `setImages(orig, result)`, `setSplitRatio(0.0-1.0)`, `setCompareMode(bool)`, zoom/pan/fit
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Create ComparisonView.h**

Create `migration_project/cpp_qt/src/widgets/ComparisonView.h`:

```cpp
#pragma once

#include <QGraphicsView>
#include <QGraphicsScene>
#include <QGraphicsPixmapItem>
#include <QImage>

class ComparisonView : public QGraphicsView {
    Q_OBJECT
public:
    explicit ComparisonView(QWidget* parent = nullptr);
    ~ComparisonView() override = default;

    void setImages(const QImage& original, const QImage& result);
    void setResultImage(const QImage& result);

    void setSplitRatio(double ratio);   // 0.0=all orig, 1.0=all result
    double splitRatio() const;

    void setCompareMode(bool enabled);
    bool isCompareMode() const;

    void fitToView();
    void zoomActual();
    void zoomIn();
    void zoomOut();
    void setZoom(double factor);
    double zoom() const;
    bool hasImage() const;

    void clearOverlays();

signals:
    void cursorMoved(int px, int py);

protected:
    void wheelEvent(QWheelEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void paintEvent(QPaintEvent* event) override;

private:
    void rebuildClip();
    void updateSceneRect();

    QGraphicsScene* m_scene;
    QGraphicsPixmapItem* m_origItem;
    QGraphicsPixmapItem* m_resultItem;
    double m_zoom = 1.0;
    double m_splitRatio = 0.5;

    bool m_compareMode = false;
    bool m_draggingSplit = false;
    bool m_panning = false;
    QPoint m_lastPanPos;
};
```

- [ ] **Step 2: Create ComparisonView.cpp**

Create `migration_project/cpp_qt/src/widgets/ComparisonView.cpp`:

```cpp
#include "ComparisonView.h"

#include <QWheelEvent>
#include <QMouseEvent>
#include <QScrollBar>
#include <QPainter>
#include <QPen>
#include <QtMath>

ComparisonView::ComparisonView(QWidget* parent)
    : QGraphicsView(parent)
    , m_scene(new QGraphicsScene(this))
    , m_origItem(nullptr)
    , m_resultItem(nullptr)
{
    setScene(m_scene);
    setRenderHint(QPainter::Antialiasing, false);
    setRenderHint(QPainter::SmoothPixmapTransform, true);
    setDragMode(QGraphicsView::NoDrag);
    setTransformationAnchor(QGraphicsView::AnchorUnderMouse);
    setResizeAnchor(QGraphicsView::AnchorUnderMouse);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setViewportUpdateMode(QGraphicsView::SmartViewportUpdate);
    setMouseTracking(true);
    setBackgroundBrush(QBrush(Qt::darkGray));
}

void ComparisonView::setImages(const QImage& original, const QImage& result) {
    m_scene->clear();
    m_origItem = m_scene->addPixmap(QPixmap::fromImage(original));
    m_resultItem = m_scene->addPixmap(QPixmap::fromImage(result));
    m_resultItem->setZValue(1);
    updateSceneRect();
    rebuildClip();
    fitToView();
}

void ComparisonView::setResultImage(const QImage& result) {
    if (m_resultItem) {
        m_resultItem->setPixmap(QPixmap::fromImage(result));
    } else {
        m_resultItem = m_scene->addPixmap(QPixmap::fromImage(result));
        m_resultItem->setZValue(1);
    }
    updateSceneRect();
    if (!m_compareMode) {
        fitToView();
    }
}

void ComparisonView::setSplitRatio(double ratio) {
    ratio = qBound(0.0, ratio, 1.0);
    if (qFuzzyCompare(ratio, m_splitRatio)) return;
    m_splitRatio = ratio;
    rebuildClip();
    viewport()->update();
}

double ComparisonView::splitRatio() const {
    return m_splitRatio;
}

void ComparisonView::setCompareMode(bool enabled) {
    m_compareMode = enabled;
    if (!enabled && m_resultItem) {
        // Show full result — no clipping
        m_resultItem->setVisible(true);
    }
    rebuildClip();
    viewport()->update();
}

bool ComparisonView::isCompareMode() const {
    return m_compareMode;
}

void ComparisonView::fitToView() {
    if (!m_resultItem && !m_origItem) return;
    QRectF r = m_scene->sceneRect();
    if (r.isEmpty()) return;
    fitInView(r, Qt::KeepAspectRatio);
    QTransform t = transform();
    m_zoom = qSqrt(t.m11() * t.m11() + t.m12() * t.m12());
}

void ComparisonView::zoomActual() {
    resetTransform();
    m_zoom = 1.0;
}

void ComparisonView::zoomIn() {
    setZoom(m_zoom * 1.25);
}

void ComparisonView::zoomOut() {
    setZoom(m_zoom / 1.25);
}

void ComparisonView::setZoom(double factor) {
    if (!m_resultItem && !m_origItem) return;
    factor = qBound(0.01, factor, 100.0);
    double ratio = factor / m_zoom;
    scale(ratio, ratio);
    m_zoom = factor;
}

double ComparisonView::zoom() const {
    return m_zoom;
}

bool ComparisonView::hasImage() const {
    return m_resultItem != nullptr || m_origItem != nullptr;
}

void ComparisonView::clearOverlays() {
    if (!m_resultItem && !m_origItem) {
        m_scene->clear();
        return;
    }
    QList<QGraphicsItem*> items = m_scene->items();
    for (auto* item : items) {
        if (item != m_origItem && item != m_resultItem) {
            m_scene->removeItem(item);
            delete item;
        }
    }
}

// --- Internal ---

void ComparisonView::rebuildClip() {
    if (!m_resultItem) return;
    if (!m_compareMode) {
        m_resultItem->setVisible(true);
        m_resultItem->setVisible(true);
        if (m_origItem) m_origItem->setVisible(false);
        return;
    }
    if (m_origItem) m_origItem->setVisible(true);

    QRectF sceneR = m_scene->sceneRect();
    if (sceneR.isEmpty()) return;

    // The result item shows from splitRatio * width to the right edge.
    // The original item shows the left portion (handled by result being on top).
    double splitX = sceneR.left() + m_splitRatio * sceneR.width();

    QPainterPath clipPath;
    clipPath.addRect(splitX, sceneR.top(),
                     sceneR.right() - splitX + 1, sceneR.height());
    m_resultItem->setVisible(true);
}

// --- Events ---

void ComparisonView::wheelEvent(QWheelEvent* event) {
    if (event->modifiers() & Qt::ControlModifier) {
        double delta = event->angleDelta().y();
        double factor = delta > 0 ? 1.15 : 1.0 / 1.15;
        setZoom(m_zoom * factor);
        event->accept();
    } else {
        QGraphicsView::wheelEvent(event);
    }
}

void ComparisonView::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton) {
        m_panning = true;
        m_lastPanPos = event->pos();
        setCursor(Qt::ClosedHandCursor);
        event->accept();
        return;
    }
    if (event->button() == Qt::LeftButton && m_compareMode) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        double splitX = r.left() + m_splitRatio * r.width();
        if (qAbs(scenePos.x() - splitX) < 10.0) {
            m_draggingSplit = true;
            event->accept();
            return;
        }
    }
    QGraphicsView::mousePressEvent(event);
}

void ComparisonView::mouseMoveEvent(QMouseEvent* event) {
    if (m_panning) {
        QPoint delta = event->pos() - m_lastPanPos;
        m_lastPanPos = event->pos();
        horizontalScrollBar()->setValue(horizontalScrollBar()->value() - delta.x());
        verticalScrollBar()->setValue(verticalScrollBar()->value() - delta.y());
        event->accept();
        return;
    }
    if (m_draggingSplit) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        if (r.width() > 0) {
            double ratio = (scenePos.x() - r.left()) / r.width();
            setSplitRatio(ratio);
        }
        event->accept();
        return;
    }
    // Change cursor near split line
    if (m_compareMode) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        double splitX = r.left() + m_splitRatio * r.width();
        if (qAbs(scenePos.x() - splitX) < 10.0)
            setCursor(Qt::SplitHCursor);
        else
            setCursor(Qt::ArrowCursor);
    }
    emit cursorMoved(static_cast<int>(mapToScene(event->pos()).x()),
                     static_cast<int>(mapToScene(event->pos()).y()));
    QGraphicsView::mouseMoveEvent(event);
}

void ComparisonView::mouseReleaseEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton && m_panning) {
        m_panning = false;
        setCursor(Qt::ArrowCursor);
        event->accept();
        return;
    }
    if (event->button() == Qt::LeftButton && m_draggingSplit) {
        m_draggingSplit = false;
        event->accept();
        return;
    }
    QGraphicsView::mouseReleaseEvent(event);
}

void ComparisonView::resizeEvent(QResizeEvent* event) {
    QGraphicsView::resizeEvent(event);
}

void ComparisonView::paintEvent(QPaintEvent* event) {
    QGraphicsView::paintEvent(event);

    // Draw the split line and handle in compare mode
    if (!m_compareMode || !m_resultItem) return;

    QRectF r = m_scene->sceneRect();
    if (r.isEmpty()) return;

    double splitX = r.left() + m_splitRatio * r.width();
    QPointF top = mapFromScene(splitX, r.top());
    QPointF bottom = mapFromScene(splitX, r.bottom());

    QPainter painter(viewport());
    QPen linePen(QColor(255, 255, 255, 200), 2);
    painter.setPen(linePen);
    painter.drawLine(top, bottom);

    // Handle grip at center
    QPointF mid = mapFromScene(splitX, r.center().y());
    QRectF gripRect(mid.x() - 6, mid.y() - 20, 12, 40);
    painter.fillRect(gripRect, QColor(255, 255, 255, 180));
    painter.setPen(QPen(QColor(60, 60, 60), 1));
    painter.drawRect(gripRect);
}

void ComparisonView::updateSceneRect() {
    QRectF r;
    if (m_resultItem)
        r = m_resultItem->boundingRect();
    else if (m_origItem)
        r = m_origItem->boundingRect();
    m_scene->setSceneRect(r);
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/widgets/ComparisonView.h migration_project/cpp_qt/src/widgets/ComparisonView.cpp
git commit -m "feat: add ComparisonView with slider comparison

- Single QGraphicsView + dual pixmap items
- Draggable split line in compare mode
- Single-image mode hides original, shows result only
- Zoom/pan/middle-button-drag inherited from QGraphicsView
- Cursor changes to SplitHCursor near line"
```

---

### Task 9: OperatorChainWidget — Batch Chain Editor

**Files:**
- Create: `cpp_qt/src/widgets/OperatorChainWidget.h`
- Create: `cpp_qt/src/widgets/OperatorChainWidget.cpp`

**Interfaces:**
- Consumes: Qt6 Widgets, shared OpDef registry (extracted from ImageProcessingTab)
- Produces: `OperatorChainWidget` — `chain()` returns `QVector<ChainStep>`, `setChain()`, `changed()` signal
- Consumed by: Task 11 (ImageProcessingTab rewrite)

- [ ] **Step 1: Extract OpDef registry to a shared header**

The `OpDef`, `ParamDef`, `addOp`, `buildRegistry`, `getRegistry`, `findOp` currently live in `ImageProcessingTab.cpp` as static file-scope entities. Extract them to a new shared header so `OperatorChainWidget` can reuse them.

Create `migration_project/cpp_qt/src/tabs/OperatorRegistry.h`:

```cpp
#pragma once

#include <QString>
#include <QVector>
#include <QVariant>
#include <QStringList>

struct ParamDef {
    QString name;
    QString i18nKey;
    QString kind;
    QVariant defVal;
    double minVal = 0, maxVal = 100, step = 1;
    QStringList choices;
};

struct OpDef {
    QString id;
    QString i18nKey;
    QString category;
    QString descI18nKey;
    QVector<ParamDef> params;
};

const QVector<OpDef>& getRegistry();
const OpDef* findOp(const QString& id);
```

- [ ] **Step 2: Move registry implementation to OperatorRegistry.cpp**

Move the existing static functions (`addOp`, `buildRegistry`, `getRegistry`, `findOp`) and the `OpDef`/`ParamDef` structs from `ImageProcessingTab.cpp` into a new file `migration_project/cpp_qt/src/tabs/OperatorRegistry.cpp`. Keep the struct definitions in the header. The implementation is identical to what's in `ImageProcessingTab.cpp` lines 27-177 — just extract to the new file.

- [ ] **Step 3: Update ImageProcessingTab.cpp to include the shared header**

Replace lines 27-177 in `ImageProcessingTab.cpp` (the OpDef/ParamDef structs + static registry functions) with:

```cpp
#include "OperatorRegistry.h"
```

Also update `ImageProcessingTab.h` to remove the forward declaration `struct OpDef;` if present.

- [ ] **Step 4: Create OperatorChainWidget.h**

Create `migration_project/cpp_qt/src/widgets/OperatorChainWidget.h`:

```cpp
#pragma once

#include <QWidget>
#include <QTableWidget>
#include <QPushButton>
#include <QVector>
#include <rstao/common/types.hpp>

struct ChainStep {
    QString opId;
    rstao::ParamMap params;

    bool isValid() const { return !opId.isEmpty(); }
};

class OperatorChainWidget : public QWidget {
    Q_OBJECT
public:
    explicit OperatorChainWidget(QWidget* parent = nullptr);

    QVector<ChainStep> chain() const;
    void setChain(const QVector<ChainStep>& steps);

signals:
    void changed();

private slots:
    void addStep();
    void removeStep();
    void editStep(int row);
    void refreshTable();

private:
    QTableWidget* m_table;
    QPushButton* m_addBtn;
    QPushButton* m_removeBtn;
    QVector<ChainStep> m_steps;
};
```

- [ ] **Step 5: Create OperatorChainWidget.cpp**

Create `migration_project/cpp_qt/src/widgets/OperatorChainWidget.cpp`:

```cpp
#include "OperatorChainWidget.h"
#include "../tabs/OperatorRegistry.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QComboBox>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QLabel>

OperatorChainWidget::OperatorChainWidget(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);

    m_table = new QTableWidget(0, 3, this);
    m_table->setHorizontalHeaderLabels({tr("Operator"), tr("Parameters"), QString()});
    m_table->horizontalHeader()->setStretchLastSection(false);
    m_table->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    m_table->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_table->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_table->setSelectionMode(QAbstractItemView::SingleSelection);
    m_table->setDragDropMode(QAbstractItemView::InternalMove);
    m_table->setDragEnabled(true);
    m_table->setAcceptDrops(true);
    m_table->setDropIndicatorShown(true);
    m_table->verticalHeader()->setDragDropMode(QAbstractItemView::InternalMove);
    layout->addWidget(m_table);

    connect(m_table, &QTableWidget::cellDoubleClicked, this, [this](int row, int /*col*/) {
        editStep(row);
    });

    auto* btnRow = new QHBoxLayout();
    btnRow->setSpacing(6);

    m_addBtn = new QPushButton(tr("Add Step"), this);
    connect(m_addBtn, &QPushButton::clicked, this, &OperatorChainWidget::addStep);
    btnRow->addWidget(m_addBtn);

    m_removeBtn = new QPushButton(tr("Remove Step"), this);
    m_removeBtn->setEnabled(false);
    connect(m_removeBtn, &QPushButton::clicked, this, &OperatorChainWidget::removeStep);
    btnRow->addWidget(m_removeBtn);

    btnRow->addStretch();
    layout->addLayout(btnRow);

    connect(m_table->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]() {
        m_removeBtn->setEnabled(m_table->currentRow() >= 0);
    });
}

QVector<ChainStep> OperatorChainWidget::chain() const {
    return m_steps;
}

void OperatorChainWidget::setChain(const QVector<ChainStep>& steps) {
    m_steps = steps;
    refreshTable();
    emit changed();
}

void OperatorChainWidget::addStep() {
    ChainStep step;
    const auto& registry = getRegistry();
    if (!registry.isEmpty()) {
        step.opId = registry.first().id;
        for (const auto& pdef : registry.first().params)
            step.params[pdef.name.toStdString()] = pdef.defVal;
    }
    m_steps.append(step);
    refreshTable();
    emit changed();
}

void OperatorChainWidget::removeStep() {
    int row = m_table->currentRow();
    if (row < 0 || row >= m_steps.size()) return;
    m_steps.removeAt(row);
    refreshTable();
    emit changed();
}

void OperatorChainWidget::editStep(int row) {
    if (row < 0 || row >= m_steps.size()) return;

    const OpDef* op = findOp(m_steps[row].opId);
    if (!op) return;

    QDialog dlg(this);
    dlg.setWindowTitle(tr("Edit Parameters"));
    auto* form = new QFormLayout(&dlg);

    QHash<QString, QWidget*> widgets;
    for (const auto& pdef : op->params) {
        QWidget* w = nullptr;
        std::string key = pdef.name.toStdString();

        if (pdef.kind == "choice") {
            auto* cb = new QComboBox(&dlg);
            cb->addItems(pdef.choices);
            if (auto* v = std::get_if<std::string>(&m_steps[row].params[key]))
                cb->setCurrentText(QString::fromStdString(*v));
            w = cb;
        } else if (pdef.kind == "int") {
            auto* sb = new QSpinBox(&dlg);
            sb->setRange(static_cast<int>(pdef.minVal), static_cast<int>(pdef.maxVal));
            sb->setSingleStep(static_cast<int>(pdef.step));
            if (auto* v = std::get_if<int>(&m_steps[row].params[key]))
                sb->setValue(*v);
            else
                sb->setValue(pdef.defVal.toInt());
            w = sb;
        } else if (pdef.kind == "double") {
            auto* dsb = new QDoubleSpinBox(&dlg);
            dsb->setRange(pdef.minVal, pdef.maxVal);
            dsb->setSingleStep(pdef.step);
            dsb->setDecimals(3);
            if (auto* v = std::get_if<double>(&m_steps[row].params[key]))
                dsb->setValue(*v);
            else
                dsb->setValue(pdef.defVal.toDouble());
            w = dsb;
        } else if (pdef.kind == "bool") {
            auto* cb = new QCheckBox(&dlg);
            if (auto* v = std::get_if<bool>(&m_steps[row].params[key]))
                cb->setChecked(*v);
            w = cb;
        }

        if (w) {
            form->addRow(pdef.name, w);
            widgets[pdef.name] = w;
        }
    }

    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dlg);
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);
    form->addRow(buttons);

    if (dlg.exec() == QDialog::Accepted) {
        for (const auto& pdef : op->params) {
            QWidget* w = widgets.value(pdef.name);
            if (!w) continue;
            std::string key = pdef.name.toStdString();
            if (auto* cb = qobject_cast<QComboBox*>(w))
                m_steps[row].params[key] = cb->currentText().toStdString();
            else if (auto* sb = qobject_cast<QSpinBox*>(w))
                m_steps[row].params[key] = sb->value();
            else if (auto* dsb = qobject_cast<QDoubleSpinBox*>(w))
                m_steps[row].params[key] = dsb->value();
            else if (auto* check = qobject_cast<QCheckBox*>(w))
                m_steps[row].params[key] = check->isChecked();
        }
        refreshTable();
        emit changed();
    }
}

void OperatorChainWidget::refreshTable() {
    m_table->setRowCount(0);
    for (int i = 0; i < m_steps.size(); ++i) {
        const auto& step = m_steps[i];
        const OpDef* op = findOp(step.opId);
        m_table->insertRow(i);

        QTableWidgetItem* nameItem = new QTableWidgetItem(op ? op->id : step.opId);
        nameItem->setFlags(nameItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 0, nameItem);

        // Params summary
        QStringList summaryParts;
        for (const auto& kv : step.params) {
            std::visit([&](const auto& val) {
                using T = std::decay_t<decltype(val)>;
                if constexpr (std::is_same_v<T, int>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::number(val);
                else if constexpr (std::is_same_v<T, double>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::number(val, 'f', 1);
                else if constexpr (std::is_same_v<T, std::string>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::fromStdString(val);
                else if constexpr (std::is_same_v<T, bool>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + (val ? "true" : "false");
            }, kv.second);
        }
        QTableWidgetItem* paramsItem = new QTableWidgetItem(summaryParts.join(", "));
        paramsItem->setFlags(paramsItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 1, paramsItem);

        QTableWidgetItem* editItem = new QTableWidgetItem(tr("Edit"));
        editItem->setFlags(editItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 2, editItem);
    }
}
```

- [ ] **Step 6: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/tabs/OperatorRegistry.h migration_project/cpp_qt/src/tabs/OperatorRegistry.cpp migration_project/cpp_qt/src/widgets/OperatorChainWidget.h migration_project/cpp_qt/src/widgets/OperatorChainWidget.cpp migration_project/cpp_qt/src/tabs/ImageProcessingTab.cpp
git commit -m "feat: add OperatorChainWidget and extract shared operator registry

- Extract OpDef/ParamDef/registry from ImageProcessingTab to OperatorRegistry
- OperatorChainWidget: add/remove/reorder chain steps
- Double-click row to edit step parameters in dialog
- Drag-reorder rows via QTableWidget internalMove"
```

---

### Task 10: ImageProcessingTab — Full Rewrite

**Files:**
- Modify: `cpp_qt/src/tabs/ImageProcessingTab.h` (add new members)
- Modify: `cpp_qt/src/tabs/ImageProcessingTab.cpp` (full rewrite of logic)

**Interfaces:**
- Consumes: `ProcessingWorker` (Task 4), `BatchWorker` (Task 5), `HistoryStack` (Task 6), `PresetManager` (Task 7), `ComparisonView` (Task 8), `OperatorChainWidget` (Task 9)
- Produces: fully functional ImageProcessingTab with all 7 features

Note: This task is the largest. It ties all previous components together and adds the state machine, drag-drop, undo/redo buttons, preset UI, batch panel, and comparison toggle. The existing `buildUi()` structure (left panel cards + right viewer area) is preserved and extended rather than replaced from scratch.

- [ ] **Step 1: Rewrite ImageProcessingTab.h**

Replace `migration_project/cpp_qt/src/tabs/ImageProcessingTab.h` with the expanded version that includes all new members:

```cpp
#pragma once

#include <QWidget>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QSpinBox>
#include <QCheckBox>
#include <QLineEdit>
#include <QGroupBox>
#include <QPushButton>
#include <QTextEdit>
#include <QSplitter>
#include <QLabel>
#include <QFormLayout>
#include <QVBoxLayout>
#include <QHash>
#include <QProgressBar>

#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

class RasterViewerWidget;
class ComparisonView;
class ProcessingWorker;
class BatchWorker;
class HistoryStack;
class PresetManager;
class ProjectModel;
class OperatorChainWidget;
struct OpDef;

enum class TabState { Idle, SingleRunning, BatchRunning };

class ImageProcessingTab : public QWidget {
    Q_OBJECT
public:
    explicit ImageProcessingTab(ProjectModel* project = nullptr, QWidget* parent = nullptr);
    ~ImageProcessingTab() override;

    void retranslateUi();

protected:
    void dragEnterEvent(QDragEnterEvent* event) override;
    void dropEvent(QDropEvent* event) override;

private slots:
    void onLoadImage();
    void onLoadReference();
    void onClear();
    void onCategoryChanged(int idx);
    void onOperatorChanged(int idx);
    void onRun();
    void onSaveResult();
    void onUndo();
    void onRedo();
    void onShowHistory();
    void onSavePreset();
    void onApplyPreset();
    void onDeletePreset();
    void onPresetSelectionChanged(int idx);
    void onCompareToggled(bool checked);
    void onBatchRun();
    void onBatchBrowseInput();
    void onBatchBrowseOutput();

private:
    void buildUi();
    QGroupBox* buildDataCard();
    QGroupBox* buildOperatorCard();
    QGroupBox* buildParamCard();
    QGroupBox* buildActionCard();
    QWidget* buildPresetRow();
    QWidget* buildBatchPanel();

    void populateCategories();
    void populateOperators(const QString& category);
    void clearParameters();
    void buildParameterWidgets(const OpDef* op);
    rstao::ParamMap collectParams();
    void updateParamLabels();
    void setState(TabState state);
    void updateButtonStates();
    void loadImageCommon(const QString& path);
    void refreshComparisonView();
    void refreshPresetCombo();
    void pushHistory(const cv::Mat& result, const QString& opId, const rstao::ParamMap& params);

    // Left panel widgets
    QGroupBox* m_dataGroup = nullptr;
    QPushButton* m_loadImageBtn = nullptr;
    QPushButton* m_loadRefBtn = nullptr;
    QPushButton* m_clearBtn = nullptr;
    QLabel* m_imagePathLabel = nullptr;

    QGroupBox* m_operatorGroup = nullptr;
    QComboBox* m_categoryCombo = nullptr;
    QComboBox* m_operatorCombo = nullptr;
    QLabel* m_operatorDesc = nullptr;

    QGroupBox* m_paramGroup = nullptr;
    QFormLayout* m_paramLayout = nullptr;
    QLabel* m_paramEmptyLabel = nullptr;
    QHash<QString, QWidget*> m_paramWidgets;

    // Preset row (inside param card)
    QComboBox* m_presetCombo = nullptr;
    QPushButton* m_savePresetBtn = nullptr;
    QPushButton* m_applyPresetBtn = nullptr;
    QPushButton* m_deletePresetBtn = nullptr;

    QGroupBox* m_actionGroup = nullptr;
    QPushButton* m_runBtn = nullptr;
    QPushButton* m_undoBtn = nullptr;
    QPushButton* m_redoBtn = nullptr;
    QPushButton* m_historyBtn = nullptr;
    QTextEdit* m_metricsEdit = nullptr;
    QProgressBar* m_progressBar = nullptr;

    // Batch panel (collapsible, below action card)
    QWidget* m_batchPanel = nullptr;
    QLineEdit* m_batchInputDir = nullptr;
    QLineEdit* m_batchOutputDir = nullptr;
    QComboBox* m_batchFormatCombo = nullptr;
    OperatorChainWidget* m_batchChain = nullptr;
    QPushButton* m_batchRunBtn = nullptr;
    QTextEdit* m_batchLog = nullptr;

    // Right panel
    QSplitter* m_rightSplitter = nullptr;
    RasterViewerWidget* m_origViewer = nullptr;
    ComparisonView* m_comparisonView = nullptr;
    QCheckBox* m_compareCheck = nullptr;
    QPushButton* m_saveResultBtn = nullptr;

    // Core
    ProcessingWorker* m_worker = nullptr;
    BatchWorker* m_batchWorker = nullptr;
    HistoryStack* m_history = nullptr;
    PresetManager* m_presets = nullptr;
    ProjectModel* m_project = nullptr;

    // State
    TabState m_state = TabState::Idle;
    cv::Mat m_resultImage;
    QString m_imagePath;
    QString m_currentOperatorId;
};
```

- [ ] **Step 2: Rewrite ImageProcessingTab.cpp body**

Replace `migration_project/cpp_qt/src/tabs/ImageProcessingTab.cpp` with the full implementation. The key structural changes:

**Constructor** — accepts `ProjectModel*`, creates all new components:
```cpp
ImageProcessingTab::ImageProcessingTab(ProjectModel* project, QWidget* parent)
    : QWidget(parent)
    , m_project(project)
    , m_history(new HistoryStack())
    , m_presets(new PresetManager(project))
    , m_worker(new ProcessingWorker(this))
    , m_batchWorker(new BatchWorker(this))
{
    setAcceptDrops(true);
    buildUi();
    populateCategories();
    retranslateUi();

    connect(m_worker, &ProcessingWorker::progress, this, [this](int pct) {
        m_progressBar->setValue(pct);
    });
    connect(m_worker, &ProcessingWorker::finished, this, [this](rstao::ProcessingResult result, QString opId, rstao::ParamMap params) {
        m_resultImage = result.image;
        pushHistory(result.image, opId, params);
        refreshComparisonView();
        QString metricsText;
        for (const auto& kv : result.metrics) {
            metricsText += QString::fromStdString(kv.first) + ": ";
            std::visit([&](const auto& v) {
                using T = std::decay_t<decltype(v)>;
                if constexpr (std::is_same_v<T, int>)
                    metricsText += QString::number(v);
                else if constexpr (std::is_same_v<T, double>)
                    metricsText += QString::number(v, 'f', 2);
                else if constexpr (std::is_same_v<T, std::string>)
                    metricsText += QString::fromStdString(v);
            }, kv.second);
            metricsText += "\n";
        }
        m_metricsEdit->setPlainText(metricsText);
        m_progressBar->setValue(100);
        setState(TabState::Idle);
    });
    connect(m_worker, &ProcessingWorker::failed, this, [this](QString msg) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"), msg);
        setState(TabState::Idle);
    });
    connect(m_worker, &ProcessingWorker::canceled, this, [this]() {
        setState(TabState::Idle);
    });

    connect(m_batchWorker, &BatchWorker::progress, m_progressBar, &QProgressBar::setValue);
    connect(m_batchWorker, &BatchWorker::batchFinished, this, [this](int succeeded, int failed) {
        m_batchLog->append(I18n::instance().tr("tab.image_processing.batch.done")
                           .arg(succeeded).arg(failed));
        setState(TabState::Idle);
    });
    connect(m_batchWorker, &BatchWorker::fileFinished, this, [this](const QString& path) {
        m_batchLog->append(I18n::instance().tr("tab.image_processing.batch.file_processed")
                           .arg(path));
    });
    connect(m_batchWorker, &BatchWorker::canceled, this, [this]() {
        setState(TabState::Idle);
    });
    connect(m_batchWorker, &BatchWorker::failed, this, [this](const QString& msg) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"), msg);
        setState(TabState::Idle);
    });

    setState(TabState::Idle);
    refreshPresetCombo();
}
```

**buildUi()** — keep the existing left panel + right splitter layout, but replace `m_resultViewer` with `ComparisonView`, add orig viewer folding, add batch panel, add preset row:

```cpp
void ImageProcessingTab::buildUi() {
    auto* outer = new QHBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);

    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left panel
    auto* leftScroll = new QScrollArea(this);
    leftScroll->setWidgetResizable(true);
    leftScroll->setMinimumWidth(320);
    leftScroll->setMaximumWidth(460);

    auto* leftWidget = new QWidget();
    auto* leftLayout = new QVBoxLayout(leftWidget);
    leftLayout->setContentsMargins(12, 12, 12, 12);
    leftLayout->setSpacing(10);

    leftLayout->addWidget(buildDataCard());
    leftLayout->addWidget(buildOperatorCard());
    leftLayout->addWidget(buildParamCard());
    leftLayout->addWidget(buildActionCard());
    leftLayout->addWidget(buildBatchPanel());
    leftLayout->addStretch(1);

    leftScroll->setWidget(leftWidget);
    splitter->addWidget(leftScroll);

    // Right panel
    auto* rightWidget = new QWidget();
    auto* rightLayout = new QVBoxLayout(rightWidget);
    rightLayout->setContentsMargins(8, 8, 8, 8);
    rightLayout->setSpacing(8);

    // Toolbar row: compare checkbox + save
    auto* toolbarRow = new QHBoxLayout();
    toolbarRow->setSpacing(8);

    m_compareCheck = new QCheckBox(rightWidget);
    connect(m_compareCheck, &QCheckBox::toggled, this, &ImageProcessingTab::onCompareToggled);
    toolbarRow->addWidget(m_compareCheck);

    toolbarRow->addStretch();

    m_saveResultBtn = new QPushButton(rightWidget);
    connect(m_saveResultBtn, &QPushButton::clicked, this, &ImageProcessingTab::onSaveResult);
    toolbarRow->addWidget(m_saveResultBtn);
    rightLayout->addLayout(toolbarRow);

    m_origViewer = new RasterViewerWidget(rightWidget);
    m_comparisonView = new ComparisonView(rightWidget);

    m_rightSplitter = new QSplitter(Qt::Horizontal, rightWidget);
    m_rightSplitter->addWidget(m_origViewer);
    m_rightSplitter->addWidget(m_comparisonView);
    m_rightSplitter->setSizes({300, 700});
    rightLayout->addWidget(m_rightSplitter, 1);

    splitter->addWidget(rightWidget);
    splitter->setSizes({360, 900});
    outer->addWidget(splitter);
}
```

**buildActionCard()** — adds Undo/Redo/History buttons + progress bar:

```cpp
QGroupBox* ImageProcessingTab::buildActionCard() {
    m_actionGroup = new QGroupBox(this);
    auto* layout = new QVBoxLayout(m_actionGroup);
    layout->setSpacing(8);

    m_runBtn = new QPushButton(m_actionGroup);
    m_runBtn->setMinimumHeight(36);
    connect(m_runBtn, &QPushButton::clicked, this, &ImageProcessingTab::onRun);
    layout->addWidget(m_runBtn);

    auto* undoRow = new QHBoxLayout();
    m_undoBtn = new QPushButton(m_actionGroup);
    m_undoBtn->setEnabled(false);
    connect(m_undoBtn, &QPushButton::clicked, this, &ImageProcessingTab::onUndo);
    undoRow->addWidget(m_undoBtn);

    m_redoBtn = new QPushButton(m_actionGroup);
    m_redoBtn->setEnabled(false);
    connect(m_redoBtn, &QPushButton::clicked, this, &ImageProcessingTab::onRedo);
    undoRow->addWidget(m_redoBtn);

    m_historyBtn = new QPushButton(m_actionGroup);
    connect(m_historyBtn, &QPushButton::clicked, this, &ImageProcessingTab::onShowHistory);
    undoRow->addWidget(m_historyBtn);
    layout->addLayout(undoRow);

    m_progressBar = new QProgressBar(m_actionGroup);
    m_progressBar->setRange(0, 100);
    m_progressBar->setValue(0);
    m_progressBar->setVisible(false);
    layout->addWidget(m_progressBar);

    m_metricsEdit = new QTextEdit(m_actionGroup);
    m_metricsEdit->setReadOnly(true);
    m_metricsEdit->setMaximumHeight(100);
    layout->addWidget(m_metricsEdit);

    return m_actionGroup;
}
```

**buildPresetRow()** — returned from `buildParamCard` bottom:

```cpp
QWidget* ImageProcessingTab::buildPresetRow() {
    auto* row = new QWidget(m_paramGroup);
    auto* layout = new QHBoxLayout(row);
    layout->setContentsMargins(0, 8, 0, 0);
    layout->setSpacing(6);

    m_presetCombo = new QComboBox(row);
    m_presetCombo->setMinimumWidth(120);
    connect(m_presetCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &ImageProcessingTab::onPresetSelectionChanged);
    layout->addWidget(m_presetCombo, 1);

    m_applyPresetBtn = new QPushButton(row);
    connect(m_applyPresetBtn, &QPushButton::clicked, this, &ImageProcessingTab::onApplyPreset);
    layout->addWidget(m_applyPresetBtn);

    m_savePresetBtn = new QPushButton(row);
    connect(m_savePresetBtn, &QPushButton::clicked, this, &ImageProcessingTab::onSavePreset);
    layout->addWidget(m_savePresetBtn);

    m_deletePresetBtn = new QPushButton(row);
    connect(m_deletePresetBtn, &QPushButton::clicked, this, &ImageProcessingTab::onDeletePreset);
    layout->addWidget(m_deletePresetBtn);

    return row;
}
```

And modify `buildParamCard()` — add the preset row at the bottom right before returning:

```cpp
QGroupBox* ImageProcessingTab::buildParamCard() {
    m_paramGroup = new QGroupBox(this);
    auto* outer = new QVBoxLayout(m_paramGroup);
    outer->setSpacing(0);

    m_paramLayout = new QFormLayout();
    m_paramLayout->setSpacing(8);
    m_paramLayout->setContentsMargins(0, 8, 0, 0);

    m_paramEmptyLabel = new QLabel(m_paramGroup);
    m_paramLayout->addRow(m_paramEmptyLabel);

    outer->addLayout(m_paramLayout);
    // Preset row at bottom — only visible when project is open
    auto* presetRow = buildPresetRow();
    outer->addWidget(presetRow);

    return m_paramGroup;
}
```

**buildBatchPanel()** — collapsible batch section:

```cpp
QWidget* ImageProcessingTab::buildBatchPanel() {
    m_batchPanel = new QGroupBox(this);
    m_batchPanel->setVisible(false);
    auto* layout = new QVBoxLayout(m_batchPanel);
    layout->setSpacing(6);

    // Input dir
    auto* inRow = new QHBoxLayout();
    auto* inLabel = new QLabel(m_batchPanel);
    inLabel->setObjectName("batchInputLabel");
    inRow->addWidget(inLabel);
    m_batchInputDir = new QLineEdit(m_batchPanel);
    inRow->addWidget(m_batchInputDir, 1);
    auto* inBrowseBtn = new QPushButton(m_batchPanel);
    inBrowseBtn->setObjectName("batchBrowseInputBtn");
    connect(inBrowseBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchBrowseInput);
    inRow->addWidget(inBrowseBtn);
    layout->addLayout(inRow);

    // Output dir
    auto* outRow = new QHBoxLayout();
    auto* outLabel = new QLabel(m_batchPanel);
    outLabel->setObjectName("batchOutputLabel");
    outRow->addWidget(outLabel);
    m_batchOutputDir = new QLineEdit(m_batchPanel);
    outRow->addWidget(m_batchOutputDir, 1);
    auto* outBrowseBtn = new QPushButton(m_batchPanel);
    outBrowseBtn->setObjectName("batchBrowseOutputBtn");
    connect(outBrowseBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchBrowseOutput);
    outRow->addWidget(outBrowseBtn);
    layout->addLayout(outRow);

    // Output format
    auto* fmtRow = new QHBoxLayout();
    auto* fmtLabel = new QLabel(m_batchPanel);
    fmtLabel->setObjectName("batchFormatLabel");
    fmtRow->addWidget(fmtLabel);
    m_batchFormatCombo = new QComboBox(m_batchPanel);
    m_batchFormatCombo->addItems({"png", "jpg", "tif"});
    fmtRow->addWidget(m_batchFormatCombo);
    fmtRow->addStretch();
    layout->addLayout(fmtRow);

    // Operator chain
    m_batchChain = new OperatorChainWidget(m_batchPanel);
    layout->addWidget(m_batchChain);

    // Run + progress + log
    m_batchRunBtn = new QPushButton(m_batchPanel);
    connect(m_batchRunBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchRun);
    layout->addWidget(m_batchRunBtn);

    m_batchLog = new QTextEdit(m_batchPanel);
    m_batchLog->setReadOnly(true);
    m_batchLog->setMaximumHeight(120);
    layout->addWidget(m_batchLog);

    return m_batchPanel;
}
```

**State machine:**

```cpp
void ImageProcessingTab::setState(TabState state) {
    m_state = state;
    updateButtonStates();
}

void ImageProcessingTab::updateButtonStates() {
    bool isIdle = (m_state == TabState::Idle);
    bool hasImage = m_history && m_history->count() > 0;
    bool hasOp = !m_currentOperatorId.isEmpty();
    bool canRun = isIdle && hasImage && hasOp;
    bool hasResult = !m_resultImage.empty();

    m_runBtn->setEnabled(canRun);
    if (m_state == TabState::SingleRunning) {
        m_runBtn->setText(I18n::instance().tr("tab.image_processing.cancel"));
        m_runBtn->setEnabled(true);
    } else {
        m_runBtn->setText(I18n::instance().tr("tab.image_processing.run"));
    }

    m_undoBtn->setEnabled(isIdle && m_history && m_history->canUndo());
    m_redoBtn->setEnabled(isIdle && m_history && m_history->canRedo());

    bool hasProject = m_presets && m_presets->isAvailable();
    m_savePresetBtn->setEnabled(isIdle && hasProject && hasOp);
    m_applyPresetBtn->setEnabled(isIdle && hasProject && m_presetCombo->currentIndex() >= 0);
    m_deletePresetBtn->setEnabled(isIdle && hasProject && m_presetCombo->currentIndex() >= 0);

    m_saveResultBtn->setEnabled(isIdle && hasResult);

    bool batchIdle = isIdle;
    m_batchRunBtn->setEnabled(batchIdle);
    if (m_state == TabState::BatchRunning) {
        m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.cancel"));
        m_batchRunBtn->setEnabled(true);
    } else {
        m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.batch.run"));
    }

    m_progressBar->setVisible(m_state != TabState::Idle);

    // Disable operator/param changes while running
    m_categoryCombo->setEnabled(isIdle);
    m_operatorCombo->setEnabled(isIdle);
    m_loadImageBtn->setEnabled(isIdle);
    m_loadRefBtn->setEnabled(isIdle);
    m_clearBtn->setEnabled(isIdle);
}
```

**Key slot implementations:**

```cpp
void ImageProcessingTab::onRun() {
    if (m_state == TabState::SingleRunning) {
        m_worker->cancel();
        return;
    }
    if (m_history->count() == 0) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            I18n::instance().tr("tab.image_processing.no_image_loaded"));
        return;
    }
    if (m_currentOperatorId.isEmpty()) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            I18n::instance().tr("tab.image_processing.no_operator_selected"));
        return;
    }
    setState(TabState::SingleRunning);
    m_progressBar->setValue(0);
    rstao::ParamMap params = collectParams();
    m_worker->run(m_history->currentImage(), m_currentOperatorId, params);
}

void ImageProcessingTab::onUndo() {
    if (!m_history || !m_history->canUndo()) return;
    m_history->undo();
    m_resultImage = m_history->currentImage();
    refreshComparisonView();
    updateButtonStates();
}

void ImageProcessingTab::onRedo() {
    if (!m_history || !m_history->canRedo()) return;
    m_history->redo();
    m_resultImage = m_history->currentImage();
    refreshComparisonView();
    updateButtonStates();
}

void ImageProcessingTab::onShowHistory() {
    if (!m_history || m_history->count() == 0) return;

    QDialog dlg(this);
    dlg.setWindowTitle(I18n::instance().tr("tab.image_processing.history.title"));
    auto* layout = new QVBoxLayout(&dlg);
    auto* list = new QListWidget(&dlg);

    for (int i = 0; i < m_history->count(); ++i) {
        const HistoryEntry* e = m_history->entryAt(i);
        QString text = QString("[%1] %2").arg(i).arg(e->description);
        QListWidgetItem* item = new QListWidgetItem(text, list);
        if (i == m_history->currentIndex()) {
            item->setBackground(QColor(200, 230, 255));
        }
    }
    layout->addWidget(list);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok, &dlg);
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    layout->addWidget(buttons);

    connect(list, &QListWidget::currentRowChanged, this, [this, &dlg](int row) {
        if (row >= 0) {
            m_history->jumpTo(row);
            m_resultImage = m_history->currentImage();
            refreshComparisonView();
            updateButtonStates();
        }
    });

    dlg.exec();
}

void ImageProcessingTab::onLoadImage() {
    QString path = QFileDialog::getOpenFileName(this,
        I18n::instance().tr("tab.image_processing.load_image_title"), QString(),
        I18n::instance().tr("tab.image_processing.image_filter"));
    if (path.isEmpty()) return;
    loadImageCommon(path);
}

void ImageProcessingTab::loadImageCommon(const QString& path) {
    try {
        m_imagePath = path;
        cv::Mat img = rstao::read_image(path.toStdString());
        m_history->initialize(img);
        m_resultImage = img;
        m_comparisonView->setResultImage(matToQImage(m_resultImage));
        m_origViewer->loadFromImage(QImage(path));
        m_imagePathLabel->setText(QFileInfo(path).fileName());
        m_metricsEdit->clear();
        updateButtonStates();
    } catch (const std::exception& e) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.load_error_title"),
            QString::fromStdString(e.what()));
    }
}

void ImageProcessingTab::dragEnterEvent(QDragEnterEvent* event) {
    if (event->mimeData()->hasUrls()) {
        for (const QUrl& url : event->mimeData()->urls()) {
            QString ext = QFileInfo(url.toLocalFile()).suffix().toLower();
            if (ext == "png" || ext == "jpg" || ext == "jpeg" ||
                ext == "tif" || ext == "tiff" || ext == "bmp") {
                event->acceptProposedAction();
                return;
            }
        }
    }
}

void ImageProcessingTab::dropEvent(QDropEvent* event) {
    if (event->mimeData()->hasUrls()) {
        for (const QUrl& url : event->mimeData()->urls()) {
            QString path = url.toLocalFile();
            if (!path.isEmpty()) {
                loadImageCommon(path);
                return;
            }
        }
    }
}

void ImageProcessingTab::onCompareToggled(bool checked) {
    m_comparisonView->setCompareMode(checked);
    if (checked) {
        // Set original image on comparison view
        if (m_history && m_history->count() > 0) {
            const cv::Mat& orig = m_history->entryAt(0)->image;
            m_comparisonView->setImages(matToQImage(orig), matToQImage(m_resultImage));
        }
    }
}

void ImageProcessingTab::pushHistory(const cv::Mat& result, const QString& opId,
                                      const rstao::ParamMap& params) {
    HistoryEntry entry;
    entry.image = result.clone();
    entry.opId = opId;
    entry.params = params;
    // Build a human-readable description
    QString desc = opId;
    const OpDef* od = findOp(opId);
    if (od) desc = od->id;
    for (const auto& kv : params) {
        std::visit([&](const auto& v) {
            using T = std::decay_t<decltype(v)>;
            if constexpr (std::is_same_v<T, int>)
                desc += " " + QString::fromStdString(kv.first) + "=" + QString::number(v);
            else if constexpr (std::is_same_v<T, double>)
                desc += " " + QString::fromStdString(kv.first) + "=" + QString::number(v, 'f', 1);
            else if constexpr (std::is_same_v<T, std::string>)
                desc += " " + QString::fromStdString(kv.first) + "=" + QString::fromStdString(v);
        }, kv.second);
    }
    entry.description = desc;
    m_history->push(entry);
}

void ImageProcessingTab::refreshComparisonView() {
    if (m_resultImage.empty()) return;
    m_comparisonView->setResultImage(matToQImage(m_resultImage));

    if (m_compareCheck->isChecked() && m_history && m_history->count() > 0) {
        const cv::Mat& orig = m_history->entryAt(0)->image;
        m_comparisonView->setImages(matToQImage(orig), matToQImage(m_resultImage));
    }
}

// --- Preset slots ---

void ImageProcessingTab::onSavePreset() {
    if (!m_presets || !m_presets->isAvailable()) return;

    bool ok = false;
    QString name = QInputDialog::getText(this,
        I18n::instance().tr("tab.image_processing.preset.save_title"),
        I18n::instance().tr("tab.image_processing.preset.name_prompt"),
        QLineEdit::Normal, QString(), &ok);
    if (!ok || name.isEmpty()) return;

    Preset p;
    p.name = name;
    p.opId = m_currentOperatorId;
    p.params = collectParams();
    m_presets->savePreset(p);
    refreshPresetCombo();
}

void ImageProcessingTab::onApplyPreset() {
    if (!m_presets || !m_presets->isAvailable()) return;
    int idx = m_presetCombo->currentIndex();
    if (idx < 0) return;

    QList<Preset> presets = m_presets->presetsForOperator(m_currentOperatorId);
    if (idx >= presets.size()) return;

    const Preset& p = presets[idx];
    // Apply params back to widgets
    for (auto it = m_paramWidgets.cbegin(); it != m_paramWidgets.cend(); ++it) {
        QWidget* w = it.value();
        std::string key = it.key().toStdString();
        auto found = p.params.find(key);
        if (found == p.params.end()) continue;

        std::visit([&](const auto& val) {
            using T = std::decay_t<decltype(val)>;
            if constexpr (std::is_same_v<T, int>) {
                if (auto* sb = qobject_cast<QSpinBox*>(w)) sb->setValue(val);
            } else if constexpr (std::is_same_v<T, double>) {
                if (auto* dsb = qobject_cast<QDoubleSpinBox*>(w)) dsb->setValue(val);
            } else if constexpr (std::is_same_v<T, std::string>) {
                if (auto* cb = qobject_cast<QComboBox*>(w))
                    cb->setCurrentText(QString::fromStdString(val));
            } else if constexpr (std::is_same_v<T, bool>) {
                if (auto* check = qobject_cast<QCheckBox*>(w)) check->setChecked(val);
            }
        }, found->second);
    }
}

void ImageProcessingTab::onDeletePreset() {
    if (!m_presets || !m_presets->isAvailable()) return;
    int idx = m_presetCombo->currentIndex();
    if (idx < 0) return;

    QList<Preset> presets = m_presets->presetsForOperator(m_currentOperatorId);
    if (idx >= presets.size()) return;

    m_presets->deletePreset(m_currentOperatorId, presets[idx].name);
    refreshPresetCombo();
}

void ImageProcessingTab::onPresetSelectionChanged(int /*idx*/) {
    updateButtonStates();
}

void ImageProcessingTab::refreshPresetCombo() {
    m_presetCombo->clear();
    if (!m_presets || !m_presets->isAvailable()) return;
    for (const auto& p : m_presets->presetsForOperator(m_currentOperatorId)) {
        m_presetCombo->addItem(p.name);
    }
    if (m_presetCombo->count() == 0) {
        m_presetCombo->addItem(I18n::instance().tr("tab.image_processing.preset.none"));
        m_presetCombo->setEnabled(false);
    } else {
        m_presetCombo->setEnabled(true);
    }
    updateButtonStates();
}

// --- Batch slots ---

void ImageProcessingTab::onBatchRun() {
    if (m_state == TabState::BatchRunning) {
        m_batchWorker->cancel();
        return;
    }

    QString inputDir = m_batchInputDir->text();
    QString outputDir = m_batchOutputDir->text();
    if (inputDir.isEmpty() || outputDir.isEmpty()) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            "Input and output directories must be set.");
        return;
    }

    QVector<ChainStep> chain = m_batchChain->chain();
    if (chain.isEmpty()) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            "Add at least one chain step.");
        return;
    }

    QDir dir(inputDir);
    QStringList filters = {"*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.bmp"};
    QStringList files;
    for (const QFileInfo& fi : dir.entryInfoList(filters, QDir::Files))
        files.append(fi.absoluteFilePath());

    if (files.isEmpty()) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            "No image files found in input directory.");
        return;
    }

    BatchRequest req;
    req.inputFiles = files;
    req.outputDir = outputDir;
    req.chain = chain;
    req.outputFormat = m_batchFormatCombo->currentText();
    m_batchLog->clear();
    setState(TabState::BatchRunning);
    m_batchWorker->run(req);
}

void ImageProcessingTab::onBatchBrowseInput() {
    QString dir = QFileDialog::getExistingDirectory(this, "Select input folder");
    if (!dir.isEmpty()) m_batchInputDir->setText(dir);
}

void ImageProcessingTab::onBatchBrowseOutput() {
    QString dir = QFileDialog::getExistingDirectory(this, "Select output folder");
    if (!dir.isEmpty()) m_batchOutputDir->setText(dir);
}
```

The remaining methods (`buildDataCard`, `buildOperatorCard`, `buildParamCard`, `onCategoryChanged`, `onOperatorChanged`, `clearParameters`, `buildParameterWidgets`, `collectParams`, `updateParamLabels`, `populateCategories`, `populateOperators`, `onLoadReference`, `onClear`, `onSaveResult`, `matToQImage`, `retranslateUi`) retain their existing logic with minor adaptations.

For `onOperatorChanged`, add `refreshPresetCombo()` at the end. For `onClear`, add `m_history->clear()` and reset undo/redo buttons.

For `retranslateUi`, add keys for the new buttons:
```cpp
void ImageProcessingTab::retranslateUi() {
    m_dataGroup->setTitle(I18n::instance().tr("tab.image_processing.data"));
    m_loadImageBtn->setText(I18n::instance().tr("tab.image_processing.load_image"));
    m_loadRefBtn->setText(I18n::instance().tr("tab.image_processing.load_reference"));
    m_clearBtn->setText(I18n::instance().tr("tab.image_processing.clear"));
    m_operatorGroup->setTitle(I18n::instance().tr("tab.image_processing.operator"));
    m_paramGroup->setTitle(I18n::instance().tr("tab.image_processing.parameters"));
    m_paramEmptyLabel->setText(I18n::instance().tr("tab.image_processing.no_operator_selected"));
    m_actionGroup->setTitle(I18n::instance().tr("tab.image_processing.actions"));
    m_runBtn->setText(I18n::instance().tr("tab.image_processing.run"));
    m_undoBtn->setText(I18n::instance().tr("tab.image_processing.undo"));
    m_redoBtn->setText(I18n::instance().tr("tab.image_processing.redo"));
    m_historyBtn->setText(I18n::instance().tr("tab.image_processing.history"));
    m_savePresetBtn->setText(I18n::instance().tr("tab.image_processing.preset.save"));
    m_applyPresetBtn->setText(I18n::instance().tr("tab.image_processing.preset.apply"));
    m_deletePresetBtn->setText(I18n::instance().tr("tab.image_processing.preset.delete"));
    m_compareCheck->setText(I18n::instance().tr("tab.image_processing.compare_mode"));
    m_saveResultBtn->setText(I18n::instance().tr("tab.image_processing.save_result"));
    m_batchPanel->setTitle(I18n::instance().tr("tab.image_processing.batch.title"));
    // batch child widgets with objectNames
    auto* inLabel = m_batchPanel->findChild<QLabel*>("batchInputLabel");
    if (inLabel) inLabel->setText(I18n::instance().tr("tab.image_processing.batch.input_dir"));
    auto* outLabel = m_batchPanel->findChild<QLabel*>("batchOutputLabel");
    if (outLabel) outLabel->setText(I18n::instance().tr("tab.image_processing.batch.output_dir"));
    auto* fmtLabel = m_batchPanel->findChild<QLabel*>("batchFormatLabel");
    if (fmtLabel) fmtLabel->setText(I18n::instance().tr("tab.image_processing.batch.format"));
    auto* inBrowseBtn = m_batchPanel->findChild<QPushButton*>("batchBrowseInputBtn");
    if (inBrowseBtn) inBrowseBtn->setText("...");
    auto* outBrowseBtn = m_batchPanel->findChild<QPushButton*>("batchBrowseOutputBtn");
    if (outBrowseBtn) outBrowseBtn->setText("...");
    m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.batch.run"));
    updateParamLabels();
}
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/tabs/ImageProcessingTab.h migration_project/cpp_qt/src/tabs/ImageProcessingTab.cpp
git commit -m "feat: rewrite ImageProcessingTab with all 7 UI polish features

- Async single-image processing via ProcessingWorker + ProgressCallback
- Full history stack with undo/redo/jump dialog
- Preset save/apply/delete via PresetManager (requires open project)
- Slider comparison via ComparisonView + compare mode toggle
- Inherent zoom sync (single-viewer comparison)
- Batch processing: operator chain + folder input/output
- Drag-drop image loading
- State machine: Idle / SingleRunning / BatchRunning
- Button state table enforcing correct enable/disable per state"
```

---

### Task 11: MainWindow Integration + I18n Keys

**Files:**
- Modify: `cpp_qt/src/MainWindow.cpp` (pass `&m_projectModel`)
- Modify: `cpp_qt/src/I18n.cpp` (new i18n keys)

**Interfaces:**
- Consumes: `ImageProcessingTab(ProjectModel*, QWidget*)` (Task 10)
- Produces: full integration into existing app

- [ ] **Step 1: Pass ProjectModel to ImageProcessingTab**

In `migration_project/cpp_qt/src/MainWindow.cpp`, change line 407 from:

```cpp
tab = new ImageProcessingTab(nullptr);
```

To:

```cpp
tab = new ImageProcessingTab(&m_projectModel, nullptr);
```

- [ ] **Step 2: Add new i18n keys**

In `migration_project/cpp_qt/src/I18n.cpp`, in the `initTexts()` method, add new keys to both the Chinese (`zh`) and English (`en`) blocks. For the Chinese block (after line 111), add:

```cpp
        {"tab.image_processing.undo", "撤销"},
        {"tab.image_processing.redo", "重做"},
        {"tab.image_processing.history", "历史"},
        {"tab.image_processing.history.title", "处理历史"},
        {"tab.image_processing.cancel", "取消"},
        {"tab.image_processing.preset.save", "保存预设"},
        {"tab.image_processing.preset.save_title", "保存预设"},
        {"tab.image_processing.preset.name_prompt", "预设名称:"},
        {"tab.image_processing.preset.apply", "应用"},
        {"tab.image_processing.preset.delete", "删除"},
        {"tab.image_processing.preset.none", "（无预设）"},
        {"tab.image_processing.compare_mode", "对比模式"},
        {"tab.image_processing.batch.title", "批处理"},
        {"tab.image_processing.batch.input_dir", "输入目录"},
        {"tab.image_processing.batch.output_dir", "输出目录"},
        {"tab.image_processing.batch.format", "输出格式"},
        {"tab.image_processing.batch.run", "开始批处理"},
        {"tab.image_processing.batch.done", "批处理完成：%1 成功，%2 失败"},
        {"tab.image_processing.batch.file_processed", "已处理: %1"},
```

For the English block (after line 263), add:

```cpp
        {"tab.image_processing.undo", "Undo"},
        {"tab.image_processing.redo", "Redo"},
        {"tab.image_processing.history", "History"},
        {"tab.image_processing.history.title", "Processing History"},
        {"tab.image_processing.cancel", "Cancel"},
        {"tab.image_processing.preset.save", "Save Preset"},
        {"tab.image_processing.preset.save_title", "Save Preset"},
        {"tab.image_processing.preset.name_prompt", "Preset name:"},
        {"tab.image_processing.preset.apply", "Apply"},
        {"tab.image_processing.preset.delete", "Delete"},
        {"tab.image_processing.preset.none", "(No presets)"},
        {"tab.image_processing.compare_mode", "Compare Mode"},
        {"tab.image_processing.batch.title", "Batch Processing"},
        {"tab.image_processing.batch.input_dir", "Input Directory"},
        {"tab.image_processing.batch.output_dir", "Output Directory"},
        {"tab.image_processing.batch.format", "Output Format"},
        {"tab.image_processing.batch.run", "Start Batch"},
        {"tab.image_processing.batch.done", "Batch complete: %1 succeeded, %2 failed"},
        {"tab.image_processing.batch.file_processed", "Processed: %1"},
```

Note: Ensure the `retranslateUi` method of `ImageProcessingTab` already uses these keys (Task 10). If any key is missing from `retranslateUi`, add it as a separate step.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/src/MainWindow.cpp migration_project/cpp_qt/src/I18n.cpp
git commit -m "feat: wire ImageProcessingTab to ProjectModel and add i18n keys

- MainWindow passes &m_projectModel to ImageProcessingTab
- Add 19 new en/zh i18n keys for undo/redo/history/preset/batch/compare"
```

---

### Task 12: CMakeLists + Build + Full Verification

**Files:**
- Modify: `cpp_qt/CMakeLists.txt` (add new source files)

- [ ] **Step 1: Add new source files to CMakeLists.txt**

In `migration_project/cpp_qt/CMakeLists.txt`, in the `SOURCES` list (starting at line 115), append:

```cmake
    src/core/ProgressableWorker.cpp
    src/core/ProcessingWorker.cpp
    src/core/BatchWorker.cpp
    src/core/HistoryStack.cpp
    src/core/PresetManager.cpp
    src/widgets/OperatorChainWidget.cpp
    src/widgets/ComparisonView.cpp
    src/tabs/OperatorRegistry.cpp
```

In the `HEADERS` list (starting at line 132), append:

```cmake
    src/core/ProgressableWorker.h
    src/core/ProcessingWorker.h
    src/core/BatchWorker.h
    src/core/HistoryStack.h
    src/core/PresetManager.h
    src/widgets/OperatorChainWidget.h
    src/widgets/ComparisonView.h
    src/tabs/OperatorRegistry.h
```

- [ ] **Step 2: Build rstao_core**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release
```
Expected: compiles without errors.

- [ ] **Step 3: Run rstao_core tests**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp\build
ctest --output-on-failure -C Release
```
Expected: all tests pass (existing + new progress/cancel tests).

- [ ] **Step 4: Build RSTaoStudio**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release
```
Expected: compiles without errors. Fix any missing includes or mismatched signatures.

- [ ] **Step 5: Launch and smoke test**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
run.bat Release
```
Expected: RSTaoStudio launches without SIGSEGV. ImageProcessingTab renders with new buttons.

Manual verification checklist:
- [ ] Load image and run an operator → progress bar fills → result updates
- [ ] Undo → reverts result; Redo → restores
- [ ] Click History → dialog shows entries, click to jump
- [ ] Drag an image file onto the tab → loads automatically
- [ ] Open/create project → preset buttons enable, save/apply/delete preset works
- [ ] Toggle Compare Mode → split line appears, draggable
- [ ] Fill batch panel: set input/output dirs, add chain steps, Run → files processed
- [ ] Cancel during Run → button returns to "Run"
- [ ] Save result → file written to chosen path

- [ ] **Step 6: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/CMakeLists.txt
git commit -m "build: add new Phase 5.5 Plan 2 source files to CMakeLists

- 8 new .cpp/.h files (core workers, history, presets, widgets)
- rstao_core and RSTaoStudio both build and link
- All tests pass"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `build_all.bat Release` completes without errors
- [ ] `ctest --output-on-failure -C Release` in cpp/build/ shows all tests pass
- [ ] `run.bat Release` launches RSTaoStudio
- [ ] Drag-drop image onto tab loads it
- [ ] Run operator → progress bar animates, result appears
- [ ] Undo/Redo work through history
- [ ] History dialog shows entries, jump works
- [ ] Preset save/apply/delete works (with open project)
- [ ] Compare mode toggle shows draggable split line
- [ ] Batch processing runs chain on folder, outputs files
- [ ] Cancel during single run stops execution
- [ ] No hardcoded paths in CMakeLists.txt
- [ ] No build artifacts tracked in git
