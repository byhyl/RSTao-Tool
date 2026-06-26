#pragma once

#include <QString>
#include <QHash>
#include <QVariant>

class I18n {
public:
    static I18n& instance();

    bool setLanguage(const QString& language);
    QString currentLanguage() const;
    QString tr(const QString& key, const QVariantHash& args = {}) const;

    static const QString DEFAULT_LANGUAGE;

private:
    I18n();
    void initTexts();

    QString m_currentLanguage;
    QHash<QString, QHash<QString, QString>> m_texts;
};
