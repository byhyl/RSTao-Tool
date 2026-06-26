#pragma once

#include <QWidget>
#include <QLabel>

class WelcomeWorkspace : public QWidget {
    Q_OBJECT
public:
    explicit WelcomeWorkspace(QWidget* parent = nullptr);
    void retranslateUi();

private:
    QLabel* m_titleLabel;
    QLabel* m_subtitleLabel;
};
