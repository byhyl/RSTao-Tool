#include "HistoryStack.h"

HistoryStack::HistoryStack() = default;

void HistoryStack::initialize(const cv::Mat& original) {
    m_entries.clear();
    m_currentIndex = -1;
    HistoryEntry e;
    e.image = original.clone();
    e.opId = QStringLiteral("_original");
    e.description = QStringLiteral("Original");
    m_entries.append(e);
    m_currentIndex = 0;
}

void HistoryStack::push(const HistoryEntry& entry) {
    if (m_entries.isEmpty()) return;

    // Discard forward history if not at tip
    while (m_entries.size() > m_currentIndex + 1)
        m_entries.removeLast();

    m_entries.append(entry);

    while (m_entries.size() > MAX_ENTRIES)
        evictOne();

    m_currentIndex = m_entries.size() - 1;
}

bool HistoryStack::pushIfNew(const HistoryEntry& entry) {
    push(entry);
    return true;
}

bool HistoryStack::canUndo() const {
    return m_currentIndex > 0;
}

bool HistoryStack::canRedo() const {
    return m_currentIndex < m_entries.size() - 1;
}

void HistoryStack::undo() {
    if (canUndo()) --m_currentIndex;
}

void HistoryStack::redo() {
    if (canRedo()) ++m_currentIndex;
}

bool HistoryStack::jumpTo(int index) {
    if (index < 0 || index >= m_entries.size()) return false;
    m_currentIndex = index;
    return true;
}

int HistoryStack::currentIndex() const {
    return m_currentIndex;
}

int HistoryStack::count() const {
    return m_entries.size();
}

const HistoryEntry* HistoryStack::entryAt(int index) const {
    if (index < 0 || index >= m_entries.size()) return nullptr;
    return &m_entries.at(index);
}

const cv::Mat& HistoryStack::currentImage() const {
    if (m_currentIndex < 0 || m_currentIndex >= m_entries.size()) {
        static cv::Mat empty;
        return empty;
    }
    return m_entries.at(m_currentIndex).image;
}

void HistoryStack::clear() {
    m_entries.clear();
    m_currentIndex = -1;
}

void HistoryStack::evictOne() {
    if (m_entries.isEmpty()) return;
    m_entries.removeFirst();
    if (m_currentIndex > 0) --m_currentIndex;
}
