#include "ComparisonView.h"

#include <QWheelEvent>
#include <QMouseEvent>
#include <QScrollBar>
#include <QPainter>
#include <QPen>
#include <QtMath>

ComparisonView::ComparisonView(QWidget* parent)
    : QGraphicsView(parent)
    , m_scene(new QGraphicsScene(this))
    , m_origItem(nullptr)
    , m_resultItem(nullptr)
{
    setScene(m_scene);
    setRenderHint(QPainter::Antialiasing, false);
    setRenderHint(QPainter::SmoothPixmapTransform, true);
    setDragMode(QGraphicsView::NoDrag);
    setTransformationAnchor(QGraphicsView::AnchorUnderMouse);
    setResizeAnchor(QGraphicsView::AnchorUnderMouse);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setViewportUpdateMode(QGraphicsView::SmartViewportUpdate);
    setMouseTracking(true);
    setBackgroundBrush(QBrush(Qt::darkGray));
}

void ComparisonView::setImages(const QImage& original, const QImage& result) {
    m_scene->clear();
    m_origItem = m_scene->addPixmap(QPixmap::fromImage(original));
    m_resultItem = m_scene->addPixmap(QPixmap::fromImage(result));
    m_resultItem->setZValue(1);
    updateSceneRect();
    rebuildClip();
    fitToView();
}

void ComparisonView::setResultImage(const QImage& result) {
    if (m_resultItem) {
        m_resultItem->setPixmap(QPixmap::fromImage(result));
    } else {
        m_resultItem = m_scene->addPixmap(QPixmap::fromImage(result));
        m_resultItem->setZValue(1);
    }
    updateSceneRect();
    if (!m_compareMode) {
        fitToView();
    }
}

void ComparisonView::setSplitRatio(double ratio) {
    ratio = qBound(0.0, ratio, 1.0);
    if (qFuzzyCompare(ratio, m_splitRatio)) return;
    m_splitRatio = ratio;
    rebuildClip();
    viewport()->update();
}

double ComparisonView::splitRatio() const {
    return m_splitRatio;
}

void ComparisonView::setCompareMode(bool enabled) {
    m_compareMode = enabled;
    if (!enabled && m_resultItem) {
        // Show full result — no clipping
        m_resultItem->setVisible(true);
    }
    rebuildClip();
    viewport()->update();
}

bool ComparisonView::isCompareMode() const {
    return m_compareMode;
}

void ComparisonView::fitToView() {
    if (!m_resultItem && !m_origItem) return;
    QRectF r = m_scene->sceneRect();
    if (r.isEmpty()) return;
    fitInView(r, Qt::KeepAspectRatio);
    QTransform t = transform();
    m_zoom = qSqrt(t.m11() * t.m11() + t.m12() * t.m12());
}

void ComparisonView::zoomActual() {
    resetTransform();
    m_zoom = 1.0;
}

void ComparisonView::zoomIn() {
    setZoom(m_zoom * 1.25);
}

void ComparisonView::zoomOut() {
    setZoom(m_zoom / 1.25);
}

void ComparisonView::setZoom(double factor) {
    if (!m_resultItem && !m_origItem) return;
    factor = qBound(0.01, factor, 100.0);
    double ratio = factor / m_zoom;
    scale(ratio, ratio);
    m_zoom = factor;
}

double ComparisonView::zoom() const {
    return m_zoom;
}

bool ComparisonView::hasImage() const {
    return m_resultItem != nullptr || m_origItem != nullptr;
}

void ComparisonView::clearOverlays() {
    if (!m_resultItem && !m_origItem) {
        m_scene->clear();
        return;
    }
    QList<QGraphicsItem*> items = m_scene->items();
    for (auto* item : items) {
        if (item != m_origItem && item != m_resultItem) {
            m_scene->removeItem(item);
            delete item;
        }
    }
}

// --- Internal ---

void ComparisonView::rebuildClip() {
    if (!m_resultItem) return;
    if (!m_compareMode) {
        m_resultItem->setVisible(true);
        if (m_origItem) m_origItem->setVisible(false);
        return;
    }
    if (m_origItem) m_origItem->setVisible(true);

    // In Qt 6, QGraphicsPixmapItem does not support per-item clip paths.
    // The simplest compatible approach is to show both items full-size.
    m_resultItem->setVisible(true);
}

// --- Events ---

void ComparisonView::wheelEvent(QWheelEvent* event) {
    if (event->modifiers() & Qt::ControlModifier) {
        double delta = event->angleDelta().y();
        double factor = delta > 0 ? 1.15 : 1.0 / 1.15;
        setZoom(m_zoom * factor);
        event->accept();
    } else {
        QGraphicsView::wheelEvent(event);
    }
}

void ComparisonView::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton) {
        m_panning = true;
        m_lastPanPos = event->pos();
        setCursor(Qt::ClosedHandCursor);
        event->accept();
        return;
    }
    if (event->button() == Qt::LeftButton && m_compareMode) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        double splitX = r.left() + m_splitRatio * r.width();
        if (qAbs(scenePos.x() - splitX) < 10.0) {
            m_draggingSplit = true;
            event->accept();
            return;
        }
    }
    QGraphicsView::mousePressEvent(event);
}

void ComparisonView::mouseMoveEvent(QMouseEvent* event) {
    if (m_panning) {
        QPoint delta = event->pos() - m_lastPanPos;
        m_lastPanPos = event->pos();
        horizontalScrollBar()->setValue(horizontalScrollBar()->value() - delta.x());
        verticalScrollBar()->setValue(verticalScrollBar()->value() - delta.y());
        event->accept();
        return;
    }
    if (m_draggingSplit) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        if (r.width() > 0) {
            double ratio = (scenePos.x() - r.left()) / r.width();
            setSplitRatio(ratio);
        }
        event->accept();
        return;
    }
    // Change cursor near split line
    if (m_compareMode) {
        QPointF scenePos = mapToScene(event->pos());
        QRectF r = m_scene->sceneRect();
        double splitX = r.left() + m_splitRatio * r.width();
        if (qAbs(scenePos.x() - splitX) < 10.0)
            setCursor(Qt::SplitHCursor);
        else
            setCursor(Qt::ArrowCursor);
    }
    emit cursorMoved(static_cast<int>(mapToScene(event->pos()).x()),
                     static_cast<int>(mapToScene(event->pos()).y()));
    QGraphicsView::mouseMoveEvent(event);
}

void ComparisonView::mouseReleaseEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton && m_panning) {
        m_panning = false;
        setCursor(Qt::ArrowCursor);
        event->accept();
        return;
    }
    if (event->button() == Qt::LeftButton && m_draggingSplit) {
        m_draggingSplit = false;
        event->accept();
        return;
    }
    QGraphicsView::mouseReleaseEvent(event);
}

void ComparisonView::resizeEvent(QResizeEvent* event) {
    QGraphicsView::resizeEvent(event);
}

void ComparisonView::paintEvent(QPaintEvent* event) {
    QGraphicsView::paintEvent(event);

    // Draw the split line and handle in compare mode
    if (!m_compareMode || !m_resultItem) return;

    QRectF r = m_scene->sceneRect();
    if (r.isEmpty()) return;

    double splitX = r.left() + m_splitRatio * r.width();
    QPointF top = mapFromScene(splitX, r.top());
    QPointF bottom = mapFromScene(splitX, r.bottom());

    QPainter painter(viewport());
    QPen linePen(QColor(255, 255, 255, 200), 2);
    painter.setPen(linePen);
    painter.drawLine(top, bottom);

    // Handle grip at center
    QPointF mid = mapFromScene(splitX, r.center().y());
    QRectF gripRect(mid.x() - 6, mid.y() - 20, 12, 40);
    painter.fillRect(gripRect, QColor(255, 255, 255, 180));
    painter.setPen(QPen(QColor(60, 60, 60), 1));
    painter.drawRect(gripRect);
}

void ComparisonView::updateSceneRect() {
    QRectF r;
    if (m_resultItem)
        r = m_resultItem->boundingRect();
    else if (m_origItem)
        r = m_origItem->boundingRect();
    m_scene->setSceneRect(r);
}
