#pragma once

#include <QWidget>
#include <QTreeWidget>
#include <QJsonObject>

class ProjectDock : public QWidget {
    Q_OBJECT
public:
    explicit ProjectDock(QWidget* parent = nullptr);

    void setProject(const QJsonObject& project, const QString& projectPath);
    void retranslateUi();

private:
    void setEmptyState();
    void addResourceGroup(QTreeWidgetItem* parent, const QString& title, const QJsonArray& items);

    QTreeWidget* m_tree;
    QJsonObject m_project;
    QString m_projectPath;
};
