#include "ProjectModel.h"

#include <QFile>
#include <QJsonDocument>
#include <QFileInfo>
#include <QDir>

ProjectModel::ProjectModel() = default;

bool ProjectModel::newProject(const QString& name, const QString& path) {
    QString now = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    m_project = QJsonObject();
    m_project["schema_version"] = SCHEMA_VERSION;
    m_project["project_name"] = name;
    m_project["created_time"] = now;
    m_project["modified_time"] = now;
    m_project["resources"] = QJsonArray();
    m_project["data_sources"] = QJsonArray();
    m_project["result_history"] = QJsonArray();
    m_project["task_history"] = QJsonArray();
    m_project["image_processing_presets"] = QJsonArray();

    m_projectPath = path;
    return saveProject();
}

bool ProjectModel::loadProject(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return false;

    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &error);
    file.close();

    if (error.error != QJsonParseError::NoError || !doc.isObject())
        return false;

    m_project = doc.object();
    m_projectPath = path;

    // Ensure minimum schema keys exist
    if (!m_project.contains("resources"))
        m_project["resources"] = QJsonArray();
    if (!m_project.contains("data_sources"))
        m_project["data_sources"] = QJsonArray();
    if (!m_project.contains("result_history"))
        m_project["result_history"] = QJsonArray();
    if (!m_project.contains("task_history"))
        m_project["task_history"] = QJsonArray();
    if (!m_project.contains("image_processing_presets"))
        m_project["image_processing_presets"] = QJsonArray();
    m_project["schema_version"] = SCHEMA_VERSION;

    return true;
}

bool ProjectModel::saveProject() {
    if (m_projectPath.isEmpty() || m_project.isEmpty())
        return false;

    m_project["modified_time"] = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    return writeJsonFile(m_projectPath, m_project);
}

bool ProjectModel::saveProjectAs(const QString& path) {
    m_projectPath = path;
    return saveProject();
}

void ProjectModel::closeProject() {
    m_project = QJsonObject();
    m_projectPath.clear();
}

bool ProjectModel::isOpen() const {
    return !m_project.isEmpty() && !m_projectPath.isEmpty();
}

QString ProjectModel::projectPath() const {
    return m_projectPath;
}

QString ProjectModel::projectName() const {
    return m_project.value("project_name").toString();
}

QDateTime ProjectModel::createdTime() const {
    return QDateTime::fromString(m_project.value("created_time").toString(), "yyyy-MM-dd hh:mm:ss");
}

QDateTime ProjectModel::modifiedTime() const {
    return QDateTime::fromString(m_project.value("modified_time").toString(), "yyyy-MM-dd hh:mm:ss");
}

int ProjectModel::schemaVersion() const {
    return m_project.value("schema_version").toInt(SCHEMA_VERSION);
}

QJsonArray ProjectModel::resources() const {
    return m_project.value("resources").toArray();
}

QJsonArray ProjectModel::dataSources() const {
    return m_project.value("data_sources").toArray();
}

QJsonArray ProjectModel::resultHistory() const {
    return m_project.value("result_history").toArray();
}

QJsonArray ProjectModel::taskHistory() const {
    return m_project.value("task_history").toArray();
}

void ProjectModel::addResource(const QJsonObject& resource) {
    QJsonArray arr = resources();
    arr.prepend(resource);
    while (arr.size() > 500)
        arr.removeLast();
    m_project["resources"] = arr;
}

void ProjectModel::addDataSource(const QJsonObject& source) {
    QJsonArray arr = dataSources();
    arr.prepend(source);
    while (arr.size() > 200)
        arr.removeLast();
    m_project["data_sources"] = arr;
}

QJsonArray ProjectModel::presets() const {
    return m_project.value("image_processing_presets").toArray();
}

void ProjectModel::setPresets(const QJsonArray& arr) {
    m_project["image_processing_presets"] = arr;
}

QJsonObject ProjectModel::toJson() const {
    return m_project;
}

bool ProjectModel::writeJsonFile(const QString& path, const QJsonObject& obj) const {
    QFileInfo fi(path);
    QDir().mkpath(fi.absolutePath());

    QString tmpPath = path + ".tmp";
    QFile file(tmpPath);
    if (!file.open(QIODevice::WriteOnly))
        return false;

    QJsonDocument doc(obj);
    file.write(doc.toJson(QJsonDocument::Indented));
    file.close();

    // Atomic rename
    QFile::remove(path);
    return QFile::rename(tmpPath, path);
}
