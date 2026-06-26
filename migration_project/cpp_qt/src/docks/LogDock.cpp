#include "LogDock.h"

#include <QVBoxLayout>

LogDock::LogDock(QWidget* parent)
    : QWidget(parent)
{
    m_output = new QPlainTextEdit(this);
    m_output->setReadOnly(true);

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->addWidget(m_output);
}

void LogDock::append(const QString& message) {
    QString stamp = QDateTime::currentDateTime().toString("hh:mm:ss");
    m_output->appendPlainText(QString("[%1] %2").arg(stamp, message));
}
