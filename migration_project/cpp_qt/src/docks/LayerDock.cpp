#include "LayerDock.h"
#include "../I18n.h"

#include <QVBoxLayout>

LayerDock::LayerDock(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);

    m_label = new QLabel(I18n::instance().tr("layers.empty"), this);
    m_label->setAlignment(Qt::AlignCenter);
    layout->addWidget(m_label);
    layout->addStretch();
}

void LayerDock::setProject(const QJsonObject& /*project*/) {
    // Placeholder — layer management will be added in a later phase
}

void LayerDock::retranslateUi() {
    m_label->setText(I18n::instance().tr("layers.empty"));
}
