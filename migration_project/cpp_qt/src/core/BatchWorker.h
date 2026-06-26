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
