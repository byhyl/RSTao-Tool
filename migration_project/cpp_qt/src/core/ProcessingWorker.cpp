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
