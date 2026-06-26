#pragma once

#include <QString>

class ThemeManager {
public:
    static ThemeManager& instance();

    QString currentTheme() const;
    bool setTheme(const QString& name);
    QString loadStyleSheet(const QString& name) const;

    static const QStringList AVAILABLE_THEMES;
    static const QString DEFAULT_THEME;

private:
    ThemeManager();

    QString m_currentTheme;
};
