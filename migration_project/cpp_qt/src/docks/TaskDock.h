#pragma once

#include <QWidget>
#include <QLabel>

class TaskDock : public QWidget {
    Q_OBJECT
public:
    explicit TaskDock(QWidget* parent = nullptr);
    void retranslateUi();

private:
    QLabel* m_label;
};
