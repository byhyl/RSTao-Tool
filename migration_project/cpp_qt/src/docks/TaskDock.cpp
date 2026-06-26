#include "TaskDock.h"
#include "../I18n.h"

#include <QVBoxLayout>

TaskDock::TaskDock(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);

    m_label = new QLabel(I18n::instance().tr("tasks.idle"), this);
    m_label->setAlignment(Qt::AlignCenter);
    layout->addWidget(m_label);
    layout->addStretch();
}

void TaskDock::retranslateUi() {
    m_label->setText(I18n::instance().tr("tasks.idle"));
}
