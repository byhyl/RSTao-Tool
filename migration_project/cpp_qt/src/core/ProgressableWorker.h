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
