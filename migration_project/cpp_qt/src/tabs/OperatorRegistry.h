#pragma once

#include <QString>
#include <QVector>
#include <QVariant>
#include <QStringList>

struct ParamDef {
    QString name;
    QString i18nKey;
    QString kind;
    QVariant defVal;
    double minVal = 0, maxVal = 100, step = 1;
    QStringList choices;
};

struct OpDef {
    QString id;
    QString i18nKey;
    QString category;
    QString descI18nKey;
    QVector<ParamDef> params;
};

const QVector<OpDef>& getRegistry();
const OpDef* findOp(const QString& id);
