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
    cv::Mat m_refImage;
    cv::Mat m_resultImage;
    QString m_imagePath;
    QString m_currentOperatorId;
};
