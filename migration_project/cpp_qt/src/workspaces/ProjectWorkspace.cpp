#include "ProjectWorkspace.h"
#include "../I18n.h"

#include <QVBoxLayout>
#include <QGroupBox>
#include <QFormLayout>
#include <QJsonArray>

ProjectWorkspace::ProjectWorkspace(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 24, 24, 24);

    m_nameLabel = new QLabel(this);
    m_nameLabel->setObjectName("AppTitle");

    m_pathLabel = new QLabel(this);
    m_pathLabel->setObjectName("MutedText");

    m_infoLabel = new QLabel(this);

    layout->addWidget(m_nameLabel);
    layout->addWidget(m_pathLabel);
    layout->addSpacing(16);
    layout->addWidget(m_infoLabel);
    layout->addStretch();
}

void ProjectWorkspace::showProject(const QJsonObject& project, const QString& projectPath) {
    if (project.isEmpty()) {
        m_nameLabel->clear();
        m_pathLabel->setText(I18n::instance().tr("project_workspace.empty"));
        m_infoLabel->clear();
        return;
    }

    m_nameLabel->setText(project.value("project_name").toString());
    m_pathLabel->setText(projectPath);

    int resCount = project.value("resources").toArray().size();
    int srcCount = project.value("data_sources").toArray().size();
    int histCount = project.value("result_history").toArray().size();

    m_infoLabel->setText(
        QString("%1: %2   %3: %4   %5: %6")
            .arg(I18n::instance().tr("project_workspace.resources"))
            .arg(resCount)
            .arg(I18n::instance().tr("project_workspace.data_sources"))
            .arg(srcCount)
            .arg(I18n::instance().tr("project_workspace.results"))
            .arg(histCount)
    );
}

void ProjectWorkspace::retranslateUi() {
    // Info will be refreshed on next showProject call
}
