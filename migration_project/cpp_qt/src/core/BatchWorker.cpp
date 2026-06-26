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
