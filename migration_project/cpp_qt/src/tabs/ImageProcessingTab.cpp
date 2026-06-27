#include "ImageProcessingTab.h"
#include "OperatorRegistry.h"
#include "../widgets/RasterViewerWidget.h"
#include "../widgets/ComparisonView.h"
#include "../widgets/OperatorChainWidget.h"
#include "../core/ProcessingWorker.h"
#include "../core/BatchWorker.h"
#include "../core/HistoryStack.h"
#include "../core/PresetManager.h"
#include "../ProjectModel.h"
#include "../I18n.h"

#include <rstao/image_processing.hpp>
#include <rstao/image_io.hpp>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QScrollArea>
#include <QFileDialog>
#include <QMessageBox>
#include <QApplication>
#include <QImageReader>
#include <QFileInfo>
#include <QVariantMap>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QComboBox>
#include <QSet>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QDir>
#include <QInputDialog>
#include <QDialog>
#include <QListWidget>
#include <QDialogButtonBox>
#include <QListWidgetItem>

// --- Helpers -------------------------------------------------------------

static QImage matToQImage(const cv::Mat& mat) {
    if (mat.empty()) return QImage();
    int type = mat.type();
    QImage img;
    if (type == CV_8UC3) {
        cv::Mat rgb;
        cv::cvtColor(mat, rgb, cv::COLOR_BGR2RGB);
        img = QImage(rgb.data, rgb.cols, rgb.rows, static_cast<int>(rgb.step),
                     QImage::Format_RGB888).copy();
    } else if (type == CV_8UC1) {
        img = QImage(mat.data, mat.cols, mat.rows, static_cast<int>(mat.step),
                     QImage::Format_Grayscale8).copy();
    } else {
        cv::Mat tmp;
        mat.convertTo(tmp, CV_8U);
        if (tmp.channels() == 1) {
            img = QImage(tmp.data, tmp.cols, tmp.rows, static_cast<int>(tmp.step),
                         QImage::Format_Grayscale8).copy();
        } else if (tmp.channels() == 4) {
            cv::Mat rgba;
            cv::cvtColor(tmp, rgba, cv::COLOR_BGRA2RGBA);
            img = QImage(rgba.data, rgba.cols, rgba.rows, static_cast<int>(rgba.step),
                         QImage::Format_RGBA8888).copy();
        } else {
            cv::Mat rgb;
            cv::cvtColor(tmp, rgb, cv::COLOR_BGR2RGB);
            img = QImage(rgb.data, rgb.cols, rgb.rows, static_cast<int>(rgb.step),
                         QImage::Format_RGB888).copy();
        }
    }
    return img;
}

// --- ImageProcessingTab --------------------------------------------------

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

    // --- Worker connections ---

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
        m_batchLog->append(I18n::instance().tr("tab.image_processing.batch.done").arg(succeeded).arg(failed));
        setState(TabState::Idle);
    });
    connect(m_batchWorker, &BatchWorker::fileFinished, this, [this](const QString& path) {
        m_batchLog->append(I18n::instance().tr("tab.image_processing.batch.file_processed").arg(path));
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

ImageProcessingTab::~ImageProcessingTab() {
    // Workers owned by QObject parent (this), auto-deleted
    delete m_history;
    delete m_presets;
}

// --- UI Construction ---

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

// --- Cards ---

QGroupBox* ImageProcessingTab::buildDataCard() {
    m_dataGroup = new QGroupBox(this);
    auto* layout = new QVBoxLayout(m_dataGroup);
    layout->setSpacing(8);

    auto* btnRow = new QHBoxLayout();
    btnRow->setSpacing(6);

    m_loadImageBtn = new QPushButton(m_dataGroup);
    connect(m_loadImageBtn, &QPushButton::clicked, this, &ImageProcessingTab::onLoadImage);
    btnRow->addWidget(m_loadImageBtn);

    m_loadRefBtn = new QPushButton(m_dataGroup);
    connect(m_loadRefBtn, &QPushButton::clicked, this, &ImageProcessingTab::onLoadReference);
    btnRow->addWidget(m_loadRefBtn);

    m_clearBtn = new QPushButton(m_dataGroup);
    connect(m_clearBtn, &QPushButton::clicked, this, &ImageProcessingTab::onClear);
    btnRow->addWidget(m_clearBtn);

    layout->addLayout(btnRow);

    m_imagePathLabel = new QLabel(m_dataGroup);
    m_imagePathLabel->setWordWrap(true);
    layout->addWidget(m_imagePathLabel);

    return m_dataGroup;
}

QGroupBox* ImageProcessingTab::buildOperatorCard() {
    m_operatorGroup = new QGroupBox(this);
    auto* layout = new QFormLayout(m_operatorGroup);
    layout->setSpacing(8);

    m_categoryCombo = new QComboBox(m_operatorGroup);
    connect(m_categoryCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &ImageProcessingTab::onCategoryChanged);
    layout->addRow(QString(), m_categoryCombo);

    m_operatorCombo = new QComboBox(m_operatorGroup);
    connect(m_operatorCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &ImageProcessingTab::onOperatorChanged);
    layout->addRow(QString(), m_operatorCombo);

    m_operatorDesc = new QLabel(m_operatorGroup);
    m_operatorDesc->setWordWrap(true);
    layout->addRow(QString(), m_operatorDesc);

    return m_operatorGroup;
}

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
    // Preset row at bottom -- only visible when project is open
    auto* presetRow = buildPresetRow();
    outer->addWidget(presetRow);

    return m_paramGroup;
}

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

QWidget* ImageProcessingTab::buildBatchPanel() {
    m_batchPanel = new QGroupBox(this);
    m_batchPanel->setVisible(false);  // collapsed by default
    auto* layout = new QVBoxLayout(m_batchPanel);
    layout->setSpacing(6);

    // Input dir
    auto* inRow = new QHBoxLayout();
    auto* inLabel = new QLabel(m_batchPanel);
    inLabel->setObjectName("batchInputLabel");
    inLabel->setText(I18n::instance().tr("tab.image_processing.batch.input_dir"));
    inRow->addWidget(inLabel);
    m_batchInputDir = new QLineEdit(m_batchPanel);
    inRow->addWidget(m_batchInputDir, 1);
    auto* inBrowseBtn = new QPushButton(m_batchPanel);
    inBrowseBtn->setObjectName("batchBrowseInputBtn");
    inBrowseBtn->setText("...");
    connect(inBrowseBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchBrowseInput);
    inRow->addWidget(inBrowseBtn);
    layout->addLayout(inRow);

    // Output dir
    auto* outRow = new QHBoxLayout();
    auto* outLabel = new QLabel(m_batchPanel);
    outLabel->setObjectName("batchOutputLabel");
    outLabel->setText(I18n::instance().tr("tab.image_processing.batch.output_dir"));
    outRow->addWidget(outLabel);
    m_batchOutputDir = new QLineEdit(m_batchPanel);
    outRow->addWidget(m_batchOutputDir, 1);
    auto* outBrowseBtn = new QPushButton(m_batchPanel);
    outBrowseBtn->setObjectName("batchBrowseOutputBtn");
    outBrowseBtn->setText("...");
    connect(outBrowseBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchBrowseOutput);
    outRow->addWidget(outBrowseBtn);
    layout->addLayout(outRow);

    // Output format
    auto* fmtRow = new QHBoxLayout();
    auto* fmtLabel = new QLabel(m_batchPanel);
    fmtLabel->setObjectName("batchFormatLabel");
    fmtLabel->setText(I18n::instance().tr("tab.image_processing.batch.format"));
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
    m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.batch.run"));
    connect(m_batchRunBtn, &QPushButton::clicked, this, &ImageProcessingTab::onBatchRun);
    layout->addWidget(m_batchRunBtn);

    m_batchLog = new QTextEdit(m_batchPanel);
    m_batchLog->setReadOnly(true);
    m_batchLog->setMaximumHeight(120);
    layout->addWidget(m_batchLog);

    return m_batchPanel;
}

// --- i18n ---

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
    if (auto* gb = qobject_cast<QGroupBox*>(m_batchPanel))
        gb->setTitle(I18n::instance().tr("tab.image_processing.batch.title"));

    // batch child widgets with objectNames
    auto* inLabel = m_batchPanel->findChild<QLabel*>("batchInputLabel");
    if (inLabel) inLabel->setText(I18n::instance().tr("tab.image_processing.batch.input_dir"));
    auto* outLabel = m_batchPanel->findChild<QLabel*>("batchOutputLabel");
    if (outLabel) outLabel->setText(I18n::instance().tr("tab.image_processing.batch.output_dir"));
    auto* fmtLabel = m_batchPanel->findChild<QLabel*>("batchFormatLabel");
    if (fmtLabel) fmtLabel->setText(I18n::instance().tr("tab.image_processing.batch.format"));
    m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.batch.run"));

    updateParamLabels();
}

// --- State Machine ---

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

    m_runBtn->setEnabled(canRun || m_state == TabState::SingleRunning);
    if (m_state == TabState::SingleRunning) {
        m_runBtn->setText(I18n::instance().tr("tab.image_processing.cancel"));
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
    m_batchRunBtn->setEnabled(batchIdle || m_state == TabState::BatchRunning);
    if (m_state == TabState::BatchRunning) {
        m_batchRunBtn->setText(I18n::instance().tr("tab.image_processing.cancel"));
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

// --- Drag and Drop ---

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

// --- Slot Implementations ---

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

void ImageProcessingTab::onLoadReference() {
    QString path = QFileDialog::getOpenFileName(this,
        I18n::instance().tr("tab.image_processing.load_reference_title"), QString(),
        I18n::instance().tr("tab.image_processing.image_filter"));
    if (path.isEmpty()) return;
    try {
        m_refImage = rstao::read_image(path.toStdString());
    } catch (const std::exception& e) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.load_error_title"),
            QString::fromStdString(e.what()));
    }
}

void ImageProcessingTab::onClear() {
    m_imagePath.clear();
    m_refImage = cv::Mat();
    m_resultImage = cv::Mat();
    m_origViewer->clearImage();
    m_comparisonView->setResultImage(QImage());
    m_imagePathLabel->clear();
    m_metricsEdit->clear();
    if (m_history) m_history->clear();
    m_undoBtn->setEnabled(false);
    m_redoBtn->setEnabled(false);
    updateButtonStates();
}

void ImageProcessingTab::onCategoryChanged(int /*idx*/) {
    populateOperators(m_categoryCombo->currentData().toString());
}

void ImageProcessingTab::onOperatorChanged(int /*idx*/) {
    clearParameters();

    QString opId = m_operatorCombo->currentData().toString();
    if (opId.isEmpty()) return;

    m_currentOperatorId = opId;
    const OpDef* op = findOp(opId);
    if (!op) return;

    m_operatorDesc->setText(I18n::instance().tr(op->descI18nKey));
    buildParameterWidgets(op);
    refreshPresetCombo();
}

void ImageProcessingTab::buildParameterWidgets(const OpDef* op) {
    clearParameters();
    m_paramEmptyLabel->setVisible(false);

    if (!op) return;
    m_paramWidgets.clear();

    for (const auto& pdef : op->params) {
        QWidget* w = nullptr;

        if (pdef.kind == "choice") {
            auto* cb = new QComboBox(m_paramGroup);
            cb->addItems(pdef.choices);
            cb->setProperty("paramName", pdef.name);
            w = cb;
        } else if (pdef.kind == "int") {
            auto* sb = new QSpinBox(m_paramGroup);
            sb->setRange(static_cast<int>(pdef.minVal), static_cast<int>(pdef.maxVal));
            sb->setSingleStep(static_cast<int>(pdef.step));
            sb->setValue(pdef.defVal.toInt());
            sb->setProperty("paramName", pdef.name);
            w = sb;
        } else if (pdef.kind == "double") {
            auto* dsb = new QDoubleSpinBox(m_paramGroup);
            dsb->setRange(pdef.minVal, pdef.maxVal);
            dsb->setSingleStep(pdef.step);
            dsb->setDecimals(3);
            dsb->setValue(pdef.defVal.toDouble());
            dsb->setProperty("paramName", pdef.name);
            w = dsb;
        } else if (pdef.kind == "bool") {
            auto* cb = new QCheckBox(m_paramGroup);
            cb->setChecked(pdef.defVal.toBool());
            cb->setProperty("paramName", pdef.name);
            w = cb;
        }

        if (w) {
            QLabel* label = new QLabel(I18n::instance().tr(pdef.i18nKey), m_paramGroup);
            label->setProperty("paramLabelKey", pdef.i18nKey);
            m_paramLayout->addRow(label, w);
            m_paramWidgets[pdef.name] = w;
        }
    }
}

void ImageProcessingTab::updateParamLabels() {
    for (int i = 0; i < m_paramLayout->rowCount(); ++i) {
        auto* item = m_paramLayout->itemAt(i, QFormLayout::LabelRole);
        if (item && item->widget()) {
            auto* label = qobject_cast<QLabel*>(item->widget());
            if (label) {
                QString key = label->property("paramLabelKey").toString();
                if (!key.isEmpty())
                    label->setText(I18n::instance().tr(key));
            }
        }
    }
    if (m_paramEmptyLabel->isVisible())
        m_paramEmptyLabel->setText(I18n::instance().tr("tab.image_processing.no_operator_selected"));
}

void ImageProcessingTab::clearParameters() {
    m_currentOperatorId.clear();
    while (m_paramLayout->rowCount() > 0)
        m_paramLayout->removeRow(m_paramLayout->rowCount() - 1);
    m_paramWidgets.clear();
    m_paramLayout->addRow(m_paramEmptyLabel);
    m_paramEmptyLabel->setVisible(true);
}

rstao::ParamMap ImageProcessingTab::collectParams() {
    rstao::ParamMap params;
    for (auto it = m_paramWidgets.cbegin(); it != m_paramWidgets.cend(); ++it) {
        QWidget* w = it.value();
        std::string name = it.key().toStdString();
        if (auto* sb = qobject_cast<QSpinBox*>(w))
            params[name] = sb->value();
        else if (auto* dsb = qobject_cast<QDoubleSpinBox*>(w))
            params[name] = dsb->value();
        else if (auto* cb = qobject_cast<QCheckBox*>(w))
            params[name] = cb->isChecked();
        else if (auto* combo = qobject_cast<QComboBox*>(w))
            params[name] = combo->currentText().toStdString();
    }
    return params;
}

// --- Run / Cancel ---

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

void ImageProcessingTab::onSaveResult() {
    if (m_resultImage.empty()) {
        QMessageBox::information(this,
            I18n::instance().tr("tab.image_processing.save_result"),
            I18n::instance().tr("tab.image_processing.no_result"));
        return;
    }
    QString path = QFileDialog::getSaveFileName(this,
        I18n::instance().tr("tab.image_processing.save_result"), QString(),
        I18n::instance().tr("tab.image_processing.save_filter"));
    if (path.isEmpty()) return;
    try {
        rstao::save_image(path.toStdString(), m_resultImage);
    } catch (const std::exception& e) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.save_result"),
            QString::fromStdString(e.what()));
    }
}

// --- Undo / Redo / History ---

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

// --- History helpers ---

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
            else if constexpr (std::is_same_v<T, bool>)
                desc += " " + QString::fromStdString(kv.first) + "=" + (v ? "true" : "false");
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
    m_presets->saveToDisk();
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
    m_presets->saveToDisk();
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
            I18n::instance().tr("tab.image_processing.batch.no_dir"));
        return;
    }

    QVector<ChainStep> chain = m_batchChain->chain();
    if (chain.isEmpty()) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            I18n::instance().tr("tab.image_processing.batch.no_chain"));
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
            I18n::instance().tr("tab.image_processing.batch.no_files"));
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
    QString dir = QFileDialog::getExistingDirectory(this, I18n::instance().tr("tab.image_processing.batch.input_browse"));
    if (!dir.isEmpty()) m_batchInputDir->setText(dir);
}

void ImageProcessingTab::onBatchBrowseOutput() {
    QString dir = QFileDialog::getExistingDirectory(this, I18n::instance().tr("tab.image_processing.batch.output_browse"));
    if (!dir.isEmpty()) m_batchOutputDir->setText(dir);
}

// --- Operator population ---

void ImageProcessingTab::populateCategories() {
    m_categoryCombo->clear();
    QSet<QString> cats;
    for (const auto& op : getRegistry())
        cats.insert(op.category);
    QStringList sorted = cats.values();
    sorted.sort();
    for (const auto& cat : sorted)
        m_categoryCombo->addItem(I18n::instance().tr(cat), cat);
    if (m_categoryCombo->count() > 0)
        populateOperators(m_categoryCombo->currentData().toString());
}

void ImageProcessingTab::populateOperators(const QString& category) {
    m_operatorCombo->clear();
    for (const auto& op : getRegistry()) {
        if (op.category == category)
            m_operatorCombo->addItem(
                I18n::instance().tr(op.i18nKey), op.id);
    }
}
