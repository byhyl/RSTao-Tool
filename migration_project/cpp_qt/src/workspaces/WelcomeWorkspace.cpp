#include "WelcomeWorkspace.h"
#include "../I18n.h"

#include <QVBoxLayout>

WelcomeWorkspace::WelcomeWorkspace(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setAlignment(Qt::AlignCenter);

    m_titleLabel = new QLabel(I18n::instance().tr("welcome.title"), this);
    m_titleLabel->setObjectName("AppTitle");
    m_titleLabel->setAlignment(Qt::AlignCenter);

    m_subtitleLabel = new QLabel(I18n::instance().tr("welcome.subtitle"), this);
    m_subtitleLabel->setObjectName("MutedText");
    m_subtitleLabel->setAlignment(Qt::AlignCenter);

    layout->addStretch();
    layout->addWidget(m_titleLabel);
    layout->addSpacing(8);
    layout->addWidget(m_subtitleLabel);
    layout->addStretch();
}

void WelcomeWorkspace::retranslateUi() {
    m_titleLabel->setText(I18n::instance().tr("welcome.title"));
    m_subtitleLabel->setText(I18n::instance().tr("welcome.subtitle"));
}
