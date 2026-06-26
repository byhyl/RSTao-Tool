#include "OperatorChainWidget.h"
#include "../tabs/OperatorRegistry.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QComboBox>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QLabel>

// --- Helper: convert QVariant + kind string to rstao::ParamValue ----

static rstao::ParamValue qVariantToParamValue(const QVariant& v, const QString& kind) {
    if (kind == "int")
        return v.toInt();
    else if (kind == "double")
        return v.toDouble();
    else if (kind == "bool")
        return v.toBool();
    else // "choice" or any other string kind
        return v.toString().toStdString();
}

OperatorChainWidget::OperatorChainWidget(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);

    m_table = new QTableWidget(0, 3, this);
    m_table->setHorizontalHeaderLabels({tr("Operator"), tr("Parameters"), QString()});
    m_table->horizontalHeader()->setStretchLastSection(false);
    m_table->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    m_table->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_table->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_table->setSelectionMode(QAbstractItemView::SingleSelection);
    m_table->setDragDropMode(QAbstractItemView::InternalMove);
    m_table->setDragEnabled(true);
    m_table->setAcceptDrops(true);
    m_table->setDropIndicatorShown(true);
    m_table->verticalHeader()->setDragDropMode(QAbstractItemView::InternalMove);
    layout->addWidget(m_table);

    connect(m_table, &QTableWidget::cellDoubleClicked, this, [this](int row, int /*col*/) {
        editStep(row);
    });

    auto* btnRow = new QHBoxLayout();
    btnRow->setSpacing(6);

    m_addBtn = new QPushButton(tr("Add Step"), this);
    connect(m_addBtn, &QPushButton::clicked, this, &OperatorChainWidget::addStep);
    btnRow->addWidget(m_addBtn);

    m_removeBtn = new QPushButton(tr("Remove Step"), this);
    m_removeBtn->setEnabled(false);
    connect(m_removeBtn, &QPushButton::clicked, this, &OperatorChainWidget::removeStep);
    btnRow->addWidget(m_removeBtn);

    btnRow->addStretch();
    layout->addLayout(btnRow);

    connect(m_table->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]() {
        m_removeBtn->setEnabled(m_table->currentRow() >= 0);
    });
}

QVector<ChainStep> OperatorChainWidget::chain() const {
    return m_steps;
}

void OperatorChainWidget::setChain(const QVector<ChainStep>& steps) {
    m_steps = steps;
    refreshTable();
    emit changed();
}

void OperatorChainWidget::addStep() {
    ChainStep step;
    const auto& registry = getRegistry();
    if (!registry.isEmpty()) {
        step.opId = registry.first().id;
        for (const auto& pdef : registry.first().params)
            step.params[pdef.name.toStdString()] = qVariantToParamValue(pdef.defVal, pdef.kind);
    }
    m_steps.append(step);
    refreshTable();
    emit changed();
}

void OperatorChainWidget::removeStep() {
    int row = m_table->currentRow();
    if (row < 0 || row >= m_steps.size()) return;
    m_steps.removeAt(row);
    refreshTable();
    emit changed();
}

void OperatorChainWidget::editStep(int row) {
    if (row < 0 || row >= m_steps.size()) return;

    const OpDef* op = findOp(m_steps[row].opId);
    if (!op) return;

    QDialog dlg(this);
    dlg.setWindowTitle(tr("Edit Parameters"));
    auto* form = new QFormLayout(&dlg);

    QHash<QString, QWidget*> widgets;
    for (const auto& pdef : op->params) {
        QWidget* w = nullptr;
        std::string key = pdef.name.toStdString();

        if (pdef.kind == "choice") {
            auto* cb = new QComboBox(&dlg);
            cb->addItems(pdef.choices);
            if (auto* v = std::get_if<std::string>(&m_steps[row].params[key]))
                cb->setCurrentText(QString::fromStdString(*v));
            w = cb;
        } else if (pdef.kind == "int") {
            auto* sb = new QSpinBox(&dlg);
            sb->setRange(static_cast<int>(pdef.minVal), static_cast<int>(pdef.maxVal));
            sb->setSingleStep(static_cast<int>(pdef.step));
            if (auto* v = std::get_if<int>(&m_steps[row].params[key]))
                sb->setValue(*v);
            else
                sb->setValue(pdef.defVal.toInt());
            w = sb;
        } else if (pdef.kind == "double") {
            auto* dsb = new QDoubleSpinBox(&dlg);
            dsb->setRange(pdef.minVal, pdef.maxVal);
            dsb->setSingleStep(pdef.step);
            dsb->setDecimals(3);
            if (auto* v = std::get_if<double>(&m_steps[row].params[key]))
                dsb->setValue(*v);
            else
                dsb->setValue(pdef.defVal.toDouble());
            w = dsb;
        } else if (pdef.kind == "bool") {
            auto* cb = new QCheckBox(&dlg);
            if (auto* v = std::get_if<bool>(&m_steps[row].params[key]))
                cb->setChecked(*v);
            w = cb;
        }

        if (w) {
            form->addRow(pdef.name, w);
            widgets[pdef.name] = w;
        }
    }

    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dlg);
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);
    form->addRow(buttons);

    if (dlg.exec() == QDialog::Accepted) {
        for (const auto& pdef : op->params) {
            QWidget* w = widgets.value(pdef.name);
            if (!w) continue;
            std::string key = pdef.name.toStdString();
            if (auto* cb = qobject_cast<QComboBox*>(w))
                m_steps[row].params[key] = cb->currentText().toStdString();
            else if (auto* sb = qobject_cast<QSpinBox*>(w))
                m_steps[row].params[key] = sb->value();
            else if (auto* dsb = qobject_cast<QDoubleSpinBox*>(w))
                m_steps[row].params[key] = dsb->value();
            else if (auto* check = qobject_cast<QCheckBox*>(w))
                m_steps[row].params[key] = check->isChecked();
        }
        refreshTable();
        emit changed();
    }
}

void OperatorChainWidget::refreshTable() {
    m_table->setRowCount(0);
    for (int i = 0; i < m_steps.size(); ++i) {
        const auto& step = m_steps[i];
        const OpDef* op = findOp(step.opId);
        m_table->insertRow(i);

        QTableWidgetItem* nameItem = new QTableWidgetItem(op ? op->id : step.opId);
        nameItem->setFlags(nameItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 0, nameItem);

        // Params summary
        QStringList summaryParts;
        for (const auto& kv : step.params) {
            std::visit([&](const auto& val) {
                using T = std::decay_t<decltype(val)>;
                if constexpr (std::is_same_v<T, int>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::number(val);
                else if constexpr (std::is_same_v<T, double>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::number(val, 'f', 1);
                else if constexpr (std::is_same_v<T, std::string>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + QString::fromStdString(val);
                else if constexpr (std::is_same_v<T, bool>)
                    summaryParts << QString::fromStdString(kv.first) + "=" + (val ? "true" : "false");
            }, kv.second);
        }
        QTableWidgetItem* paramsItem = new QTableWidgetItem(summaryParts.join(", "));
        paramsItem->setFlags(paramsItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 1, paramsItem);

        QTableWidgetItem* editItem = new QTableWidgetItem(tr("Edit"));
        editItem->setFlags(editItem->flags() & ~Qt::ItemIsEditable);
        m_table->setItem(i, 2, editItem);
    }
}
