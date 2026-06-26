#pragma once

#include <QWidget>
#include <QLabel>
#include <QJsonObject>

class PropertiesDock : public QWidget {
    Q_OBJECT
public:
    explicit PropertiesDock(QWidget* parent = nullptr);
    void showProject(const QJsonObject& project, const QString& projectPath);
    void retranslateUi();

private:
    QLabel* m_label;
};
