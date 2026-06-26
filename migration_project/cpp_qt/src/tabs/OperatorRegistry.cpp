#include "OperatorRegistry.h"

// --- Helper ---

static void addOp(QVector<OpDef>& ops,
                  const QString& id, const QString& i18nKey,
                  const QString& category, const QString& descI18nKey,
                  const QVector<ParamDef>& params = {})
{
    OpDef op;
    op.id = id;
    op.i18nKey = i18nKey;
    op.category = category;
    op.descI18nKey = descI18nKey;
    op.params = params;
    ops.append(op);
}

static QVector<OpDef> buildRegistry() {
    QVector<OpDef> ops;

    addOp(ops, "grayscale", "op.grayscale", "cat.color", "op.grayscale.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "target"; pd.i18nKey = "param.target"; pd.kind = "choice";
        pd.defVal = "HSV"; pd.choices = {"HSV","HLS","Lab","YCrCb","GRAY"};
        p.append(pd);
        addOp(ops, "color_space", "op.color_space", "cat.color", "op.color_space.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "low_percent"; pd.i18nKey = "param.low_percent"; pd.kind = "double";
        pd.defVal = 2.0; pd.minVal = 0; pd.maxVal = 49; pd.step = 1; p.append(pd);
        pd.name = "high_percent"; pd.i18nKey = "param.high_percent"; pd.kind = "double";
        pd.defVal = 98.0; pd.minVal = 51; pd.maxVal = 100; pd.step = 1; p.append(pd);
        addOp(ops, "linear_stretch", "op.linear_stretch", "cat.enhance", "op.linear_stretch.desc", p);
    }
    addOp(ops, "histogram_equalization", "op.hist_eq", "cat.enhance", "op.hist_eq.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "gaussian"; pd.choices = {"gaussian","median","bilateral","box"};
        p.append(pd);
        pd.name = "ksize"; pd.i18nKey = "param.ksize"; pd.kind = "int";
        pd.defVal = 5; pd.minVal = 3; pd.maxVal = 31; pd.step = 2; p.append(pd);
        addOp(ops, "smooth", "op.smooth", "cat.filter", "op.smooth.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "unsharp_mask"; pd.choices = {"unsharp_mask","laplacian"};
        p.append(pd);
        pd.name = "amount"; pd.i18nKey = "param.amount"; pd.kind = "double";
        pd.defVal = 1.0; pd.minVal = 0.1; pd.maxVal = 5.0; pd.step = 0.1; p.append(pd);
        addOp(ops, "sharpen", "op.sharpen", "cat.filter", "op.sharpen.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "mode"; pd.i18nKey = "param.mode"; pd.kind = "choice";
        pd.defVal = "magnitude"; pd.choices = {"magnitude","sobel","laplacian","canny","direction"};
        p.append(pd);
        addOp(ops, "edge_detect", "op.edge_detect", "cat.filter", "op.edge_detect.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "operation"; pd.i18nKey = "param.operation"; pd.kind = "choice";
        pd.defVal = "erode"; pd.choices = {"erode","dilate","open","close","gradient","tophat","blackhat"};
        p.append(pd);
        pd.name = "ksize"; pd.i18nKey = "param.ksize"; pd.kind = "int";
        pd.defVal = 3; pd.minVal = 3; pd.maxVal = 15; pd.step = 2; p.append(pd);
        pd.name = "iterations"; pd.i18nKey = "param.iterations"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 10; pd.step = 1; p.append(pd);
        addOp(ops, "morphology", "op.morphology", "cat.filter", "op.morphology.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "method"; pd.i18nKey = "param.method"; pd.kind = "choice";
        pd.defVal = "otsu"; pd.choices = {"otsu","manual","adaptive_mean","adaptive_gaussian"};
        p.append(pd);
        pd.name = "threshold"; pd.i18nKey = "param.threshold"; pd.kind = "double";
        pd.defVal = 127; pd.minVal = 0; pd.maxVal = 255; pd.step = 1; p.append(pd);
        pd.name = "block_size"; pd.i18nKey = "param.block_size"; pd.kind = "int";
        pd.defVal = 11; pd.minVal = 3; pd.maxVal = 51; pd.step = 2; p.append(pd);
        addOp(ops, "threshold", "op.threshold", "cat.segment", "op.threshold.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "component"; pd.i18nKey = "param.component"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 10; pd.step = 1; p.append(pd);
        addOp(ops, "pca", "op.pca", "cat.transform", "op.pca.desc", p);
    }
    addOp(ops, "ihs_intensity", "op.ihs_intensity", "cat.color", "op.ihs_intensity.desc");

    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "mode"; pd.i18nKey = "param.fft_mode"; pd.kind = "choice";
        pd.defVal = "lowpass"; pd.choices = {"lowpass","highpass"};
        p.append(pd);
        pd.name = "radius"; pd.i18nKey = "param.radius"; pd.kind = "double";
        pd.defVal = 30; pd.minVal = 1; pd.maxVal = 500; pd.step = 1; p.append(pd);
        addOp(ops, "fft_filter", "op.fft_filter", "cat.filter", "op.fft_filter.desc", p);
    }
    {
        QVector<ParamDef> p;
        ParamDef pd;
        pd.name = "band_a"; pd.i18nKey = "param.band_a"; pd.kind = "int";
        pd.defVal = 1; pd.minVal = 1; pd.maxVal = 99; pd.step = 1; p.append(pd);
        pd.name = "band_b"; pd.i18nKey = "param.band_b"; pd.kind = "int";
        pd.defVal = 2; pd.minVal = 1; pd.maxVal = 99; pd.step = 1; p.append(pd);
        addOp(ops, "normalized_difference", "op.normalized_difference", "cat.transform", "op.normalized_difference.desc", p);
    }

    return ops;
}

const QVector<OpDef>& getRegistry() {
    static QVector<OpDef> ops = buildRegistry();
    return ops;
}

const OpDef* findOp(const QString& id) {
    for (const auto& op : getRegistry())
        if (op.id == id) return &op;
    return nullptr;
}
