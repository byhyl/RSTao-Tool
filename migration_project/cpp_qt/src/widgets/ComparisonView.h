#pragma once

#include <QGraphicsView>
#include <QGraphicsScene>
#include <QGraphicsPixmapItem>
#include <QImage>

class ComparisonView : public QGraphicsView {
    Q_OBJECT
public:
    explicit ComparisonView(QWidget* parent = nullptr);
    ~ComparisonView() override = default;

    void setImages(const QImage& original, const QImage& result);
    void setResultImage(const QImage& result);

    void setSplitRatio(double ratio);   // 0.0=all orig, 1.0=all result
    double splitRatio() const;

    void setCompareMode(bool enabled);
    bool isCompareMode() const;

    void fitToView();
    void zoomActual();
    void zoomIn();
    void zoomOut();
    void setZoom(double factor);
    double zoom() const;
    bool hasImage() const;

    void clearOverlays();

signals:
    void cursorMoved(int px, int py);

protected:
    void wheelEvent(QWheelEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void paintEvent(QPaintEvent* event) override;

private:
    void rebuildClip();
    void updateSceneRect();

    QGraphicsScene* m_scene;
    class ClippedPixmapItem* m_origItem;
    class ClippedPixmapItem* m_resultItem;
    double m_zoom = 1.0;
    double m_splitRatio = 0.5;

    bool m_compareMode = false;
    bool m_draggingSplit = false;
    bool m_panning = false;
    QPoint m_lastPanPos;
};
