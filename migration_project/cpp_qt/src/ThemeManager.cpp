#include "ThemeManager.h"

#include <QApplication>
#include <QFile>

const QStringList ThemeManager::AVAILABLE_THEMES = {"light", "dark"};
const QString ThemeManager::DEFAULT_THEME = "light";

ThemeManager& ThemeManager::instance() {
    static ThemeManager inst;
    return inst;
}

ThemeManager::ThemeManager() : m_currentTheme(DEFAULT_THEME) {}

QString ThemeManager::currentTheme() const {
    return m_currentTheme;
}

bool ThemeManager::setTheme(const QString& name) {
    if (!AVAILABLE_THEMES.contains(name))
        return false;
    m_currentTheme = name;
    auto* app = qobject_cast<QApplication*>(QApplication::instance());
    if (app) {
        app->setStyleSheet(loadStyleSheet(name));
    }
    return true;
}

QString ThemeManager::loadStyleSheet(const QString& name) const {
    QString path = QStringLiteral(":/theme/%1.qss").arg(name);
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return {};
    return QString::fromUtf8(file.readAll());
}
