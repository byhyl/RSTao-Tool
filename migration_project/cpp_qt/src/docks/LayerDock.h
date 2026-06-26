#pragma once

#include <QWidget>
#include <QLabel>
#include <QJsonObject>

class LayerDock : public QWidget {
    Q_OBJECT
public:
    explicit LayerDock(QWidget* parent = nullptr);
    void setProject(const QJsonObject& project);
    void retranslateUi();

private:
    QLabel* m_label;
};
