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
