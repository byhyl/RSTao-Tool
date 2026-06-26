#pragma once

#include <QString>
#include <QVector>
#include <opencv2/core.hpp>
#include <rstao/common/types.hpp>

struct HistoryEntry {
    cv::Mat image;
    QString opId;
    rstao::ParamMap params;
    QString description;
};

class HistoryStack {
public:
    HistoryStack();

    void initialize(const cv::Mat& original);
    void push(const HistoryEntry& entry);
    bool pushIfNew(const HistoryEntry& entry);  // returns true if actually pushed

    bool canUndo() const;
    bool canRedo() const;
    void undo();
    void redo();
    bool jumpTo(int index);

    int currentIndex() const;
    int count() const;
    const HistoryEntry* entryAt(int index) const;
    const cv::Mat& currentImage() const;
    void clear();

private:
    void evictOne();

    QVector<HistoryEntry> m_entries;
    int m_currentIndex = -1;
    static constexpr int MAX_ENTRIES = 20;
};
