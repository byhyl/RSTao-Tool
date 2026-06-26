#include "ProjectDock.h"
#include "../I18n.h"

#include <QVBoxLayout>
#include <QJsonArray>
#include <QFileInfo>

ProjectDock::ProjectDock(QWidget* parent)
    : QWidget(parent)
{
    m_tree = new QTreeWidget(this);
    m_tree->setHeaderHidden(true);

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->addWidget(m_tree);

    setEmptyState();
}

void ProjectDock::setEmptyState() {
    m_tree->clear();
    auto* root = new QTreeWidgetItem({I18n::instance().tr("project.none")});
    root->setFlags(root->flags() & ~Qt::ItemIsEnabled);
    m_tree->addTopLevelItem(root);
}

void ProjectDock::setProject(const QJsonObject& project, const QString& projectPath) {
    m_project = project;
    m_projectPath = projectPath;
    m_tree->clear();

    if (project.isEmpty()) {
        setEmptyState();
        return;
    }

    QString name = project.value("project_name").toString();
    if (name.isEmpty())
        name = I18n::instance().tr("project.untitled");

    auto* root = new QTreeWidgetItem({name});
    root->setExpanded(true);
    m_tree->addTopLevelItem(root);

    if (!projectPath.isEmpty()) {
        auto* loc = new QTreeWidgetItem({
            QString("%1: %2").arg(I18n::instance().tr("project.file"),
                                  QFileInfo(projectPath).fileName())
        });
        loc->setToolTip(0, projectPath);
        root->addChild(loc);
    }

    addResourceGroup(root, I18n::instance().tr("project.resources"), project.value("resources").toArray());
    addResourceGroup(root, I18n::instance().tr("project.data_sources"), project.value("data_sources").toArray());
    addResourceGroup(root, I18n::instance().tr("project.results"), project.value("result_history").toArray());

    m_tree->expandAll();
}

void ProjectDock::addResourceGroup(QTreeWidgetItem* parent, const QString& title, const QJsonArray& items) {
    auto* group = new QTreeWidgetItem({title});
    parent->addChild(group);

    if (items.isEmpty()) {
        auto* empty = new QTreeWidgetItem({I18n::instance().tr("project.empty")});
        empty->setFlags(empty->flags() & ~Qt::ItemIsEnabled);
        group->addChild(empty);
        return;
    }

    int count = 0;
    for (const auto& val : items) {
        QJsonObject item = val.toObject();
        ++count;
        QString label = item.value("name").toString()
            .isEmpty() ? item.value("title").toString() : item.value("name").toString();
        QString path = item.value("source_path").toString();
        if (path.isEmpty()) path = item.value("path").toString();
        if (label.isEmpty())
            label = path.isEmpty() ? I18n::instance().tr("project.item").arg(count) : QFileInfo(path).fileName();

        auto* child = new QTreeWidgetItem({label});
        if (!path.isEmpty())
            child->setToolTip(0, path);
        group->addChild(child);
    }
}

void ProjectDock::retranslateUi() {
    setProject(m_project, m_projectPath);
}
