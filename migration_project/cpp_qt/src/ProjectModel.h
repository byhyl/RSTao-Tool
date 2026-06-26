#pragma once

#include <QString>
#include <QJsonObject>
#include <QJsonArray>
#include <QDateTime>

class ProjectModel {
public:
    ProjectModel();

    bool newProject(const QString& name, const QString& path);
    bool loadProject(const QString& path);
    bool saveProject();
    bool saveProjectAs(const QString& path);
    void closeProject();

    bool isOpen() const;
    QString projectPath() const;
    QString projectName() const;
    QDateTime createdTime() const;
    QDateTime modifiedTime() const;
    int schemaVersion() const;

    QJsonArray resources() const;
    QJsonArray dataSources() const;
    QJsonArray resultHistory() const;
    QJsonArray taskHistory() const;

    void addResource(const QJsonObject& resource);
    void addDataSource(const QJsonObject& source);

    QJsonObject toJson() const;

    static const int SCHEMA_VERSION = 4;

private:
    bool writeJsonFile(const QString& path, const QJsonObject& obj) const;

    QJsonObject m_project;
    QString m_projectPath;
};
