#pragma once

#include <QWidget>
#include <QTableWidget>
#include <QPushButton>
#include <QVector>
#include <rstao/common/types.hpp>

struct ChainStep {
    QString opId;
    rstao::ParamMap params;

    bool isValid() const { return !opId.isEmpty(); }
};

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
    QTableWidget* m_table;
    QPushButton* m_addBtn;
    QPushButton* m_removeBtn;
    QVector<ChainStep> m_steps;
};
