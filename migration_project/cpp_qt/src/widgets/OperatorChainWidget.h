#pragma once

#include <QWidget>
#include <QTableWidget>
#include <QPushButton>
#include <QVector>
#include "../core/BatchWorker.h"  // ChainStep defined here

class OperatorChainWidget : public QWidget {
    Q_OBJECT
public:
    explicit OperatorChainWidget(QWidget* parent = nullptr);

    QVector<ChainStep> chain() const;
    void setChain(const QVector<ChainStep>& steps);

signals:
    void changed();

private slots:
    void addStep();
    void removeStep();
    void editStep(int row);
    void refreshTable();

private:
    void syncStepsFromTable();

    QTableWidget* m_table;
    QPushButton* m_addBtn;
    QPushButton* m_removeBtn;
    QVector<ChainStep> m_steps;
};
