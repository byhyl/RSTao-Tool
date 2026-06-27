#include "PresetManager.h"
#include "../ProjectModel.h"

#include <QJsonObject>
#include <QJsonDocument>

PresetManager::PresetManager(ProjectModel* project)
    : m_project(project)
{
}

bool PresetManager::isAvailable() const {
    return m_project && m_project->isOpen();
}

QList<Preset> PresetManager::presetsForOperator(const QString& opId) const {
    QList<Preset> result;
    for (const auto& v : presetsArray()) {
        QJsonObject obj = v.toObject();
        if (obj.value("opId").toString() == opId)
            result.append(fromJson(obj));
    }
    return result;
}

QList<Preset> PresetManager::allPresets() const {
    QList<Preset> result;
    for (const auto& v : presetsArray()) {
        result.append(fromJson(v.toObject()));
    }
    return result;
}

void PresetManager::savePreset(const Preset& preset) {
    QJsonArray arr = presetsArray();

    // Overwrite if same opId + name exists
    for (int i = 0; i < arr.size(); ++i) {
        QJsonObject obj = arr[i].toObject();
        if (obj.value("opId").toString() == preset.opId &&
            obj.value("name").toString() == preset.name) {
            arr[i] = toJson(preset);
            writePresetsArray(arr);
            return;
        }
    }
    arr.append(toJson(preset));
    writePresetsArray(arr);
}

bool PresetManager::deletePreset(const QString& opId, const QString& name) {
    QJsonArray arr = presetsArray();
    for (int i = 0; i < arr.size(); ++i) {
        QJsonObject obj = arr[i].toObject();
        if (obj.value("opId").toString() == opId &&
            obj.value("name").toString() == name) {
            arr.removeAt(i);
            writePresetsArray(arr);
            return true;
        }
    }
    return false;
}

QJsonArray PresetManager::presetsArray() const {
    if (!m_project) return QJsonArray();
    return m_project->presets();
}

void PresetManager::writePresetsArray(const QJsonArray& arr) {
    if (!m_project) return;
    m_project->setPresets(arr);
}

void PresetManager::saveToDisk() {
    if (m_project) m_project->saveProject();
}

Preset PresetManager::fromJson(const QJsonObject& obj) {
    Preset p;
    p.name = obj.value("name").toString();
    p.opId = obj.value("opId").toString();

    QJsonObject paramsObj = obj.value("params").toObject();
    for (auto it = paramsObj.constBegin(); it != paramsObj.constEnd(); ++it) {
        QJsonValue v = it.value();
        std::string key = it.key().toStdString();
        if (v.isDouble()) {
            // Heuristic: if the value is an integer-looking double, store as int
            double d = v.toDouble();
            if (d == static_cast<int>(d))
                p.params[key] = static_cast<int>(d);
            else
                p.params[key] = d;
        } else if (v.isBool()) {
            p.params[key] = v.toBool();
        } else if (v.isString()) {
            p.params[key] = v.toString().toStdString();
        }
    }
    return p;
}

QJsonObject PresetManager::toJson(const Preset& p) {
    QJsonObject obj;
    obj["name"] = p.name;
    obj["opId"] = p.opId;

    QJsonObject paramsObj;
    for (const auto& kv : p.params) {
        QString key = QString::fromStdString(kv.first);
        std::visit([&](const auto& val) {
            using T = std::decay_t<decltype(val)>;
            if constexpr (std::is_same_v<T, int>)
                paramsObj[key] = val;
            else if constexpr (std::is_same_v<T, double>)
                paramsObj[key] = val;
            else if constexpr (std::is_same_v<T, std::string>)
                paramsObj[key] = QString::fromStdString(val);
            else if constexpr (std::is_same_v<T, bool>)
                paramsObj[key] = val;
        }, kv.second);
    }
    obj["params"] = paramsObj;
    return obj;
}
