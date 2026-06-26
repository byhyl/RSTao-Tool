#pragma once

#include <QWidget>
#include <QPlainTextEdit>
#include <QDateTime>

class LogDock : public QWidget {
    Q_OBJECT
public:
    explicit LogDock(QWidget* parent = nullptr);
    void append(const QString& message);

private:
    QPlainTextEdit* m_output;
};
