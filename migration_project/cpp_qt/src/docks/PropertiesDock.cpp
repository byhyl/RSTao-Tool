#include "PropertiesDock.h"
#include "../I18n.h"

#include <QFileInfo>
#include <QJsonArray>
#include <QVBoxLayout>
#include <QFormLayout>
#include <QGroupBox>

PropertiesDock::PropertiesDock(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);

    m_label = new QLabel(I18n::instance().tr("properties.none"), this);
    m_label->setAlignment(Qt::AlignCenter);
    m_label->setWordWrap(true);
    layout->addWidget(m_label);
    layout->addStretch();
}

void PropertiesDock::showProject(const QJsonObject& project, const QString& projectPath) {
    auto* lay = qobject_cast<QVBoxLayout*>(layout());
    if (!lay) return;

    QLayoutItem* item;
    while ((item = lay->takeAt(0)) != nullptr) {
        if (item->widget() && item->widget() != m_label)
            item->widget()->deleteLater();
        delete item;
    }

    if (project.isEmpty()) {
        m_label->setText(I18n::instance().tr("properties.none"));
        lay->addWidget(m_label);
        lay->addStretch();
        return;
    }

    m_label->setText(I18n::instance().tr("properties.selection"));
    lay->addWidget(m_label);

    auto* form = new QFormLayout();
    form->addRow(I18n::instance().tr("properties.name"), new QLabel(project.value("project_name").toString()));
    form->addRow(I18n::instance().tr("properties.path"), new QLabel(projectPath));
    form->addRow(I18n::instance().tr("properties.schema"),
                 new QLabel(QString::number(project.value("schema_version").toInt())));
    form->addRow(I18n::instance().tr("properties.modified"),
                 new QLabel(project.value("modified_time").toString()));

    auto* counts = new QFormLayout();
    counts->addRow(I18n::instance().tr("properties.resources"),
                   new QLabel(QString::number(project.value("resources").toArray().size())));
    counts->addRow(I18n::instance().tr("properties.data_sources"),
                   new QLabel(QString::number(project.value("data_sources").toArray().size())));
    counts->addRow(I18n::instance().tr("properties.results"),
                   new QLabel(QString::number(project.value("result_history").toArray().size())));

    lay->addLayout(form);
    lay->addSpacing(12);
    lay->addLayout(counts);
    lay->addStretch();
}

void PropertiesDock::retranslateUi() {
    m_label->setText(I18n::instance().tr("properties.none"));
}
