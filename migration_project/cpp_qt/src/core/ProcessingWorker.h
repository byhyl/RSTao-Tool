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
