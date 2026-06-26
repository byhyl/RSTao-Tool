#pragma once

#include <QGraphicsView>
#include <QGraphicsScene>
#include <QGraphicsPixmapItem>
#include <QImage>
#include <QPixmap>
#include <QPointF>

class RasterViewerWidget : public QGraphicsView {
    Q_OBJECT
public:
    explicit RasterViewerWidget(QWidget* parent = nullptr);
    ~RasterViewerWidget() override = default;

    bool loadFromFile(const QString& path);
    void loadFromImage(const QImage& image);
    void clearImage();

    void fitToView();
    void zoomActual();
    void zoomIn();
    void zoomOut();

    // Overlay management
    void clearOverlays();
    void addRect(const QRectF& rect, const QColor& color, double width, const QString& label = "");
    void addPoint(const QPointF& pt, const QColor& color, double radius, const QString& label = "");

    void setZoom(double factor);
    double zoom() const;

    bool hasImage() const;

signals:
    void cursorMoved(int px, int py, double geoX, double geoY);

protected:
    void wheelEvent(QWheelEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;

private:
    void emitCursorCoords(const QPointF& scenePos);
    QPointF imageToGeo(double px, double py) const;

    QGraphicsScene* m_scene;
    QGraphicsPixmapItem* m_pixmapItem;
    double m_zoom;
    bool m_panning;
    QPoint m_lastPanPos;
    bool m_hasGeoTransform;
    double m_geoTransform[6];  // GDAL-style affine transform
};
