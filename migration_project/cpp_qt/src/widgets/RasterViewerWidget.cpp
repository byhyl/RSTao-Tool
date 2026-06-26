#include "RasterViewerWidget.h"

#include <QWheelEvent>
#include <QMouseEvent>
#include <QScrollBar>
#include <QGraphicsTextItem>
#include <QGraphicsRectItem>
#include <QGraphicsEllipseItem>
#include <QPen>
#include <QFont>
#include <QImageReader>
#include <QtMath>
#include <QApplication>

RasterViewerWidget::RasterViewerWidget(QWidget* parent)
    : QGraphicsView(parent)
    , m_scene(new QGraphicsScene(this))
    , m_pixmapItem(nullptr)
    , m_zoom(1.0)
    , m_panning(false)
    , m_hasGeoTransform(false)
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

    memset(m_geoTransform, 0, sizeof(m_geoTransform));
    m_geoTransform[1] = 1.0;
    m_geoTransform[5] = -1.0;
}

bool RasterViewerWidget::loadFromFile(const QString& path) {
    QImageReader reader(path);
    reader.setAutoTransform(true);
    QImage img = reader.read();
    if (img.isNull())
        return false;

    loadFromImage(img);
    return true;
}

void RasterViewerWidget::loadFromImage(const QImage& image) {
    m_scene->clear();
    m_pixmapItem = m_scene->addPixmap(QPixmap::fromImage(image));
    m_scene->setSceneRect(m_pixmapItem->boundingRect());
    fitToView();
}

void RasterViewerWidget::clearImage() {
    m_scene->clear();
    m_pixmapItem = nullptr;
    m_scene->setSceneRect(QRectF());
}

void RasterViewerWidget::fitToView() {
    if (!m_pixmapItem) return;
    fitInView(m_scene->sceneRect(), Qt::KeepAspectRatio);
    // Compute zoom from transform
    QTransform t = transform();
    m_zoom = qSqrt(t.m11() * t.m11() + t.m12() * t.m12());
}

void RasterViewerWidget::zoomActual() {
    resetTransform();
    m_zoom = 1.0;
}

void RasterViewerWidget::zoomIn() {
    setZoom(m_zoom * 1.25);
}

void RasterViewerWidget::zoomOut() {
    setZoom(m_zoom / 1.25);
}

void RasterViewerWidget::setZoom(double factor) {
    if (!m_pixmapItem) return;
    factor = qBound(0.01, factor, 100.0);
    double ratio = factor / m_zoom;
    scale(ratio, ratio);
    m_zoom = factor;
}

double RasterViewerWidget::zoom() const {
    return m_zoom;
}

bool RasterViewerWidget::hasImage() const {
    return m_pixmapItem != nullptr;
}

// --- Overlays ---

void RasterViewerWidget::clearOverlays() {
    // Remove non-pixmap items (overlays); pixmapItem is at index 0 if it exists
    if (!m_pixmapItem) {
        m_scene->clear();
        return;
    }
    QList<QGraphicsItem*> items = m_scene->items();
    for (auto* item : items) {
        if (item != m_pixmapItem) {
            m_scene->removeItem(item);
            delete item;
        }
    }
}

void RasterViewerWidget::addRect(const QRectF& rect, const QColor& color, double width, const QString& label) {
    QPen pen(color, width);
    m_scene->addRect(rect, pen);
    if (!label.isEmpty()) {
        auto* text = m_scene->addText(label, QFont("Arial", 9));
        text->setDefaultTextColor(color);
        text->setPos(rect.left(), rect.top() - 14);
    }
}

void RasterViewerWidget::addPoint(const QPointF& pt, const QColor& color, double radius, const QString& label) {
    QPen pen(color, 1.5);
    QBrush brush(color);
    QRectF oval(pt.x() - radius, pt.y() - radius, radius * 2, radius * 2);
    m_scene->addEllipse(oval, pen, brush);

    if (!label.isEmpty()) {
        auto* text = m_scene->addText(label, QFont("Arial", 9));
        text->setDefaultTextColor(color);
        text->setPos(pt.x() + radius + 2, pt.y() - radius);
    }
}

// --- Events ---

void RasterViewerWidget::wheelEvent(QWheelEvent* event) {
    if (event->modifiers() & Qt::ControlModifier) {
        double delta = event->angleDelta().y();
        double factor = delta > 0 ? 1.15 : 1.0 / 1.15;
        setZoom(m_zoom * factor);
        event->accept();
    } else {
        QGraphicsView::wheelEvent(event);
    }
}

void RasterViewerWidget::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton) {
        m_panning = true;
        m_lastPanPos = event->pos();
        setCursor(Qt::ClosedHandCursor);
        event->accept();
        return;
    }
    if (event->button() == Qt::LeftButton) {
        emitCursorCoords(mapToScene(event->pos()));
    }
    QGraphicsView::mousePressEvent(event);
}

void RasterViewerWidget::mouseMoveEvent(QMouseEvent* event) {
    if (m_panning) {
        QPoint delta = event->pos() - m_lastPanPos;
        m_lastPanPos = event->pos();
        horizontalScrollBar()->setValue(horizontalScrollBar()->value() - delta.x());
        verticalScrollBar()->setValue(verticalScrollBar()->value() - delta.y());
        event->accept();
        return;
    }
    // Emit cursor position
    QPointF scenePos = mapToScene(event->pos());
    emitCursorCoords(scenePos);
    QGraphicsView::mouseMoveEvent(event);
}

void RasterViewerWidget::mouseReleaseEvent(QMouseEvent* event) {
    if (event->button() == Qt::MiddleButton && m_panning) {
        m_panning = false;
        setCursor(Qt::ArrowCursor);
        event->accept();
        return;
    }
    QGraphicsView::mouseReleaseEvent(event);
}

void RasterViewerWidget::resizeEvent(QResizeEvent* event) {
    QGraphicsView::resizeEvent(event);
}

// --- Helpers ---

void RasterViewerWidget::emitCursorCoords(const QPointF& scenePos) {
    int px = qRound(scenePos.x());
    int py = qRound(scenePos.y());
    QPointF geo = imageToGeo(px, py);
    emit cursorMoved(px, py, geo.x(), geo.y());
}

QPointF RasterViewerWidget::imageToGeo(double px, double py) const {
    if (!m_hasGeoTransform) {
        return QPointF(px, py);
    }
    double gx = m_geoTransform[0] + px * m_geoTransform[1] + py * m_geoTransform[2];
    double gy = m_geoTransform[3] + px * m_geoTransform[4] + py * m_geoTransform[5];
    return QPointF(gx, gy);
}
