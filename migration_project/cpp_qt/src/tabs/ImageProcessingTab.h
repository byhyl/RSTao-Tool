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

#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

class RasterViewerWidget;
struct OpDef;

class ImageProcessingTab : public QWidget {
    Q_OBJECT
public:
    explicit ImageProcessingTab(QWidget* parent = nullptr);
    ~ImageProcessingTab() override = default;

    void retranslateUi();

private slots:
    void onLoadImage();
    void onLoadReference();
    void onClear();
    void onCategoryChanged(int idx);
    void onOperatorChanged(int idx);
    void onRun();
    void onSaveResult();

private:
    void buildUi();
    QGroupBox* buildDataCard();
    QGroupBox* buildOperatorCard();
    QGroupBox* buildParamCard();
    QGroupBox* buildActionCard();

    void populateCategories();
    void populateOperators(const QString& category);
    void clearParameters();
    void buildParameterWidgets(const OpDef* op);
    rstao::ParamMap collectParams();
    void updateParamLabels();

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

    QGroupBox* m_actionGroup = nullptr;
    QPushButton* m_runBtn = nullptr;
    QTextEdit* m_metricsEdit = nullptr;

    // Right panel
    QSplitter* m_viewerSplit = nullptr;
    RasterViewerWidget* m_origViewer = nullptr;
    RasterViewerWidget* m_resultViewer = nullptr;
    QPushButton* m_saveResultBtn = nullptr;

    // State
    cv::Mat m_origImage;
    cv::Mat m_refImage;
    cv::Mat m_resultImage;
    QString m_imagePath;
    QString m_currentOperatorId;
};
