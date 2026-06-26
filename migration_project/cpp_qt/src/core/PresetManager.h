#pragma once

#include <QString>
#include <QList>
#include <QJsonArray>
#include <rstao/common/types.hpp>

class ProjectModel;

struct Preset {
    QString name;
    QString opId;
    rstao::ParamMap params;
};

class PresetManager {
public:
    explicit PresetManager(ProjectModel* project);

    QList<Preset> presetsForOperator(const QString& opId) const;
    QList<Preset> allPresets() const;
    void savePreset(const Preset& preset);     // same name overwrites
    bool deletePreset(const QString& opId, const QString& name);

    bool isAvailable() const;   // false when project is null or not open

private:
    QJsonArray presetsArray() const;
    void writePresetsArray(const QJsonArray& arr);
    static Preset fromJson(const QJsonObject& obj);
    static QJsonObject toJson(const Preset& p);

    ProjectModel* m_project;
};
