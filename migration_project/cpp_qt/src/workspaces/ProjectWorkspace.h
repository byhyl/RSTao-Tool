#pragma once

#include <QWidget>
#include <QLabel>
#include <QJsonObject>

class ProjectWorkspace : public QWidget {
    Q_OBJECT
public:
    explicit ProjectWorkspace(QWidget* parent = nullptr);
    void showProject(const QJsonObject& project, const QString& projectPath);
    void retranslateUi();

private:
    QLabel* m_nameLabel;
    QLabel* m_pathLabel;
    QLabel* m_infoLabel;
};
