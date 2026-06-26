#include "ImageProcessingTab.h"
#include "../widgets/RasterViewerWidget.h"
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

// --- Operator registry ---------------------------------------------------

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

static void addOp(QVector<OpDef>& ops,
                  const QString& id, const QString& i18nKey,
                  const QString& category, const QString& descI18nKey,
                  const QVector<ParamDef>& params = {})
{
    OpDef op;
    op.id = id;
    op.i18nKey = i18nKey;
    op.category = category;
    op.descI18nKey = descI18nKey;
    op.params = params;
    ops.append(op);
}

static QVector<OpDef> buildRegistry() {
    QVector<OpDef> ops;

    addOp(ops, "grayscale", "op.grayscale", "cat.color", "op.grayscale.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "target"; pd.i18nKey = "param.target"; pd.kind = "choice";
        pd.defVal = "HSV"; pd.choices = {"HSV","HLS","Lab","YCrCb","GRAY"};
        p.append(pd);
        addOp(ops, "color_space", "op.color_space", "cat.color", "op.color_space.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "low_percent"; pd.i18nKey = "param.low_percent"; pd.kind = "double";
        pd.defVal = 2.0; pd.minVal = 0; pd.maxVal = 49; pd.step = 1; p.append(pd);
        pd.name = "high_percent"; pd.i18nKey = "param.high_percent"; pd.kind = "double";
        pd.defVal = 98.0; pd.minVal = 51; pd.maxVal = 100; pd.step = 1; p.append(pd);
        addOp(ops, "linear_stretch", "op.linear_stretch", "cat.enhance", "op.linear_stretch.desc", p);
    }
    addOp(ops, "histogram_equalization", "op.hist_eq", "cat.enhance", "op.hist_eq.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "gaussian"; pd.choices = {"gaussian","median","bilateral","box"};
        p.append(pd);
        pd.name = "ksize"; pd.i18nKey = "param.ksize"; pd.kind = "int";
        pd.defVal = 5; pd.minVal = 3; pd.maxVal = 31; pd.step = 2; p.append(pd);
        addOp(ops, "smooth", "op.smooth", "cat.filter", "op.smooth.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "unsharp_mask"; pd.choices = {"unsharp_mask","laplacian"};
        p.append(pd);
        pd.name = "amount"; pd.i18nKey = "param.amount"; pd.kind = "double";
        pd.defVal = 1.0; pd.minVal = 0.1; pd.maxVal = 5.0; pd.step = 0.1; p.append(pd);
        addOp(ops, "sharpen", "op.sharpen", "cat.filter", "op.sharpen.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "mode"; pd.i18nKey = "param.mode"; pd.kind = "choice";
        pd.defVal = "magnitude"; pd.choices = {"magnitude","sobel","laplacian","canny","direction"};
        p.append(pd);
        addOp(ops, "edge_detect", "op.edge_detect", "cat.filter", "op.edge_detect.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "operation"; pd.i18nKey = "param.operation"; pd.kind = "choice";
        pd.defVal = "erode"; pd.choices = {"erode","dilate","open","close","gradient","tophat","blackhat"};
        p.append(pd);
        pd.name = "ksize"; pd.i18nKey = "param.ksize"; pd.kind = "int";
        pd.defVal = 3; pd.minVal = 3; pd.maxVal = 15; pd.step = 2; p.append(pd);
        pd.name = "iterations"; pd.i18nKey = "param.iterations"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 10; pd.step = 1; p.append(pd);
        addOp(ops, "morphology", "op.morphology", "cat.filter", "op.morphology.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "otsu"; pd.choices = {"otsu","manual","adaptive_mean","adaptive_gaussian"};
        p.append(pd);
        pd.name = "threshold"; pd.i18nKey = "param.threshold"; pd.kind = "double";
        pd.defVal = 127; pd.minVal = 0; pd.maxVal = 255; pd.step = 1; p.append(pd);
        pd.name = "block_size"; pd.i18nKey = "param.block_size"; pd.kind = "int";
        pd.defVal = 11; pd.minVal = 3; pd.maxVal = 51; pd.step = 2; p.append(pd);
        addOp(ops, "threshold", "op.threshold", "cat.segment", "op.threshold.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "component"; pd.i18nKey = "param.component"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 10; pd.step = 1; p.append(pd);
        addOp(ops, "pca", "op.pca", "cat.transform", "op.pca.desc", p);
    }
    addOp(ops, "ihs_intensity", "op.ihs_intensity", "cat.color", "op.ihs_intensity.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "mode"; pd.i18nKey = "param.fft_mode"; pd.kind = "choice";
        pd.defVal = "lowpass"; pd.choices = {"lowpass","highpass"};
        p.append(pd);
        pd.name = "radius"; pd.i18nKey = "param.radius"; pd.kind = "double";
        pd.defVal = 30; pd.minVal = 1; pd.maxVal = 500; pd.step = 1; p.append(pd);
        addOp(ops, "fft_filter", "op.fft_filter", "cat.filter", "op.fft_filter.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "band_a"; pd.i18nKey = "param.band_a"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 99; pd.step = 1; p.append(pd);
        pd.name = "band_b"; pd.i18nKey = "param.band_b"; pd.kind = "int";
        pd.defVal = 2; pd.minVal = 1; pd.maxVal = 99; pd.step = 1; p.append(pd);
        addOp(ops, "normalized_difference", "op.normalized_difference", "cat.transform", "op.normalized_difference.desc", p);
    }

    return ops;
}

static const QVector<OpDef>& getRegistry() {
    static QVector<OpDef> ops = buildRegistry();
    return ops;
}

static const OpDef* findOp(const QString& id) {
    for (const auto& op : getRegistry())
        if (op.id == id) return &op;
    return nullptr;
}

// --- ImageProcessingTab --------------------------------------------------

ImageProcessingTab::ImageProcessingTab(QWidget* parent)
    : QWidget(parent)
{
    buildUi();
    populateCategories();
    retranslateUi();
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
    leftLayout->addStretch(1);

    leftScroll->setWidget(leftWidget);
    splitter->addWidget(leftScroll);

    // Right panel
    auto* rightWidget = new QWidget();
    auto* rightLayout = new QVBoxLayout(rightWidget);
    rightLayout->setContentsMargins(8, 8, 8, 8);
    rightLayout->setSpacing(8);

    m_origViewer = new RasterViewerWidget(rightWidget);
    m_resultViewer = new RasterViewerWidget(rightWidget);

    m_viewerSplit = new QSplitter(Qt::Horizontal, rightWidget);
    m_viewerSplit->addWidget(m_origViewer);
    m_viewerSplit->addWidget(m_resultViewer);
    m_viewerSplit->setSizes({500, 500});
    rightLayout->addWidget(m_viewerSplit, 1);

    auto* btnRow = new QHBoxLayout();
    btnRow->setSpacing(8);
    btnRow->addStretch();

    m_saveResultBtn = new QPushButton(rightWidget);
    connect(m_saveResultBtn, &QPushButton::clicked, this, &ImageProcessingTab::onSaveResult);
    btnRow->addWidget(m_saveResultBtn);
    rightLayout->addLayout(btnRow);

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
    m_paramLayout = new QFormLayout(m_paramGroup);
    m_paramLayout->setSpacing(8);
    m_paramLayout->setContentsMargins(0, 8, 0, 0);

    m_paramEmptyLabel = new QLabel(m_paramGroup);
    m_paramLayout->addRow(m_paramEmptyLabel);

    return m_paramGroup;
}

QGroupBox* ImageProcessingTab::buildActionCard() {
    m_actionGroup = new QGroupBox(this);
    auto* layout = new QVBoxLayout(m_actionGroup);
    layout->setSpacing(8);

    m_runBtn = new QPushButton(m_actionGroup);
    m_runBtn->setMinimumHeight(36);
    connect(m_runBtn, &QPushButton::clicked, this, &ImageProcessingTab::onRun);
    layout->addWidget(m_runBtn);

    m_metricsEdit = new QTextEdit(m_actionGroup);
    m_metricsEdit->setReadOnly(true);
    m_metricsEdit->setMaximumHeight(100);
    layout->addWidget(m_metricsEdit);

    return m_actionGroup;
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
    m_saveResultBtn->setText(I18n::instance().tr("tab.image_processing.save_result"));
    updateParamLabels();
}

// --- Slots ---

void ImageProcessingTab::onLoadImage() {
    QString path = QFileDialog::getOpenFileName(this,
        I18n::instance().tr("tab.image_processing.load_image_title"), QString(),
        I18n::instance().tr("tab.image_processing.image_filter"));
    if (path.isEmpty()) return;

    try {
        m_imagePath = path;
        m_origImage = rstao::read_image(path.toStdString());
        m_origViewer->loadFromImage(QImage(path));
        m_imagePathLabel->setText(QFileInfo(path).fileName());
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
    m_origImage = cv::Mat();
    m_refImage = cv::Mat();
    m_resultImage = cv::Mat();
    m_origViewer->clearImage();
    m_resultViewer->clearImage();
    m_imagePathLabel->clear();
    m_metricsEdit->clear();
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

static QImage matToQImage(const cv::Mat& mat) {
    if (mat.empty()) return QImage();
    int type = mat.type();
    QImage img;
    if (type == CV_8UC3) {
        img = QImage(mat.data, mat.cols, mat.rows, static_cast<int>(mat.step),
                     QImage::Format_RGB888).copy();
    } else if (type == CV_8UC1) {
        img = QImage(mat.data, mat.cols, mat.rows, static_cast<int>(mat.step),
                     QImage::Format_Grayscale8).copy();
    } else {
        cv::Mat tmp;
        mat.convertTo(tmp, CV_8U);
        if (tmp.channels() == 1)
            img = QImage(tmp.data, tmp.cols, tmp.rows, static_cast<int>(tmp.step),
                         QImage::Format_Grayscale8).copy();
        else
            img = QImage(tmp.data, tmp.cols, tmp.rows, static_cast<int>(tmp.step),
                         QImage::Format_RGB888).copy();
    }
    return img;
}

void ImageProcessingTab::onRun() {
    if (m_origImage.empty()) {
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

    QApplication::setOverrideCursor(Qt::WaitCursor);
    try {
        rstao::ParamMap params = collectParams();

        rstao::ProcessingResult result = rstao::process(
            m_origImage, m_currentOperatorId.toStdString(), params);

        m_resultImage = result.image;
        m_resultViewer->loadFromImage(matToQImage(m_resultImage));

        QString metricsText;
        for (const auto& kv : result.metrics) {
            metricsText += QString::fromStdString(kv.first) + ": ";
            if (auto* v = std::get_if<int>(&kv.second))
                metricsText += QString::number(*v);
            else if (auto* v = std::get_if<double>(&kv.second))
                metricsText += QString::number(*v, 'f', 2);
            else if (auto* v = std::get_if<std::string>(&kv.second))
                metricsText += QString::fromStdString(*v);
            metricsText += "\n";
        }
        m_metricsEdit->setPlainText(metricsText);
    } catch (const std::exception& e) {
        QMessageBox::warning(this,
            I18n::instance().tr("tab.image_processing.run_error_title"),
            QString::fromStdString(e.what()));
    }
    QApplication::restoreOverrideCursor();
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
