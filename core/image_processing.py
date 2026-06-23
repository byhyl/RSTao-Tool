"""Core image processing operators used by UI and batch workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import cv2
import numpy as np

from common.exceptions import AlgorithmError


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    kind: str
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    options: tuple[str, ...] = ()
    option_labels: Mapping[str, str] = field(default_factory=dict)
    visible_when: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    help_text: str = ""

    def display_value(self, value: Any) -> str:
        return self.option_labels.get(str(value), str(value))

    def raw_value(self, value: Any) -> Any:
        if self.kind != "choice":
            return value
        text = str(value)
        if text in self.options:
            return text
        for raw, label in self.option_labels.items():
            if text == label:
                return raw
        return text

    def display_options(self) -> tuple[str, ...]:
        return tuple(self.display_value(option) for option in self.options)

    def is_visible(self, params: Mapping[str, Any]) -> bool:
        for dep_name, allowed_values in self.visible_when.items():
            if str(params.get(dep_name)) not in {str(value) for value in allowed_values}:
                return False
        return True


@dataclass(frozen=True)
class OperatorSpec:
    id: str
    name: str
    category: str
    description: str
    parameters: tuple[ParameterSpec, ...] = ()
    supports_color: bool = True
    supports_multiband: bool = False
    preview_hint: str = "image"
    tags: tuple[str, ...] = ()
    usage: str = ""


@dataclass
class ProcessingResult:
    image: np.ndarray
    metrics: Dict[str, Any] = field(default_factory=dict)
    display_image: Optional[np.ndarray] = None


class ImageProcessingCore:
    """Reusable OpenCV/NumPy image processing engine."""

    def __init__(self):
        self._operators: Dict[
            str, tuple[OperatorSpec, Callable[[np.ndarray, Dict], ProcessingResult]]
        ] = {}
        self._register_default_operators()

    def list_operators(self, category: str | None = None) -> List[OperatorSpec]:
        specs = [item[0] for item in self._operators.values()]
        if category:
            specs = [spec for spec in specs if spec.category == category]
        return sorted(specs, key=lambda spec: (spec.category, spec.name))

    def categories(self) -> List[str]:
        return sorted({spec.category for spec in self.list_operators()})

    def get_operator(self, operator_id: str) -> OperatorSpec:
        try:
            return self._operators[operator_id][0]
        except KeyError as exc:
            raise AlgorithmError(f"未知图像处理算子: {operator_id}") from exc

    def default_params(self, operator_id: str) -> Dict[str, Any]:
        return {param.name: param.default for param in self.get_operator(operator_id).parameters}

    def normalize_params(self, operator_id: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        spec = self.get_operator(operator_id)
        normalized = dict(params)
        for param in spec.parameters:
            if param.name in normalized and param.kind == "choice":
                normalized[param.name] = param.raw_value(normalized[param.name])
        return normalized

    def active_parameters(
        self, operator_id: str, params: Optional[Mapping[str, Any]] = None
    ) -> List[ParameterSpec]:
        spec = self.get_operator(operator_id)
        values = self.default_params(operator_id)
        if params:
            values.update(self.normalize_params(operator_id, params))
        return [param for param in spec.parameters if param.is_visible(values)]

    def process(
        self, image: np.ndarray, operator_id: str, params: Optional[Mapping[str, Any]] = None
    ) -> ProcessingResult:
        if image is None:
            raise AlgorithmError("输入影像为空")
        if operator_id not in self._operators:
            raise AlgorithmError(f"未知图像处理算子: {operator_id}")
        spec, func = self._operators[operator_id]
        merged = self.default_params(operator_id)
        if params:
            merged.update(self.normalize_params(operator_id, dict(params)))
        try:
            arr = np.asarray(image)
            result = func(arr, merged)
            if not isinstance(result, ProcessingResult):
                result = ProcessingResult(np.asarray(result))
            result.metrics.setdefault("operator", spec.name)
            result.metrics.setdefault("operator_id", spec.id)
            result.metrics.setdefault("dtype", str(result.image.dtype))
            result.metrics.setdefault("shape", tuple(int(v) for v in result.image.shape))
            return result
        except AlgorithmError:
            raise
        except Exception as exc:
            raise AlgorithmError(f"{spec.name}处理失败: {exc}") from exc

    def _register(
        self,
        spec: OperatorSpec,
        func: Callable[[np.ndarray, Dict], ProcessingResult],
    ) -> None:
        self._operators[spec.id] = (spec, func)

    def _register_default_operators(self) -> None:
        p = ParameterSpec
        self._register(
            OperatorSpec(
                "grayscale",
                "灰度化",
                "灰度与色彩",
                "将彩色影像转换为单通道灰度影像。",
            ),
            self._grayscale,
        )
        self._register(
            OperatorSpec(
                "color_space",
                "色彩空间转换",
                "灰度与色彩",
                "RGB/BGR 到 HSV、Lab、YCrCb 等常见空间转换。",
                (
                    p(
                        "target",
                        "目标空间",
                        "choice",
                        "HSV",
                        options=("HSV", "HLS", "Lab", "YCrCb", "GRAY"),
                        option_labels={
                            "HSV": "HSV(色相-饱和度-明度)",
                            "HLS": "HLS(色相-亮度-饱和度)",
                            "Lab": "Lab(亮度-色度)",
                            "YCrCb": "YCrCb(亮度-色差)",
                            "GRAY": "GRAY(灰度)",
                        },
                    ),
                ),
                usage="选择目标色彩空间后执行转换；GRAY 会输出单通道灰度图。",
            ),
            self._color_space,
        )
        self._register(
            OperatorSpec(
                "linear_stretch",
                "线性拉伸",
                "拉伸增强",
                "按百分比截断后进行线性动态范围拉伸。",
                (
                    p("low_percent", "低截断(%)", "float", 2.0, 0.0, 20.0, 0.5),
                    p("high_percent", "高截断(%)", "float", 98.0, 80.0, 100.0, 0.5),
                ),
                supports_multiband=True,
            ),
            self._linear_stretch,
        )
        self._register(
            OperatorSpec(
                "standard_deviation_stretch",
                "均值方差拉伸",
                "拉伸增强",
                "以均值为中心按标准差倍数增强对比度。",
                (p("sigma", "标准差倍数", "float", 2.0, 0.5, 5.0, 0.1),),
                supports_multiband=True,
            ),
            self._std_stretch,
        )
        self._register(
            OperatorSpec(
                "gamma",
                "Gamma 校正",
                "拉伸增强",
                "通过 Gamma 曲线调整整体亮度和暗部细节。",
                (p("gamma", "Gamma", "float", 1.2, 0.1, 5.0, 0.1),),
                supports_multiband=True,
            ),
            self._gamma,
        )
        self._register(
            OperatorSpec(
                "hist_equalization",
                "直方图均衡",
                "直方图",
                "单通道均衡或对彩色影像亮度通道均衡。",
            ),
            self._hist_equalization,
        )
        self._register(
            OperatorSpec(
                "clahe",
                "CLAHE 局部均衡",
                "直方图",
                "限制对比度的自适应直方图均衡。",
                (
                    p("clip_limit", "限制阈值", "float", 2.0, 0.5, 10.0, 0.1),
                    p("tile_size", "网格大小", "int", 8, 2, 32, 1),
                ),
            ),
            self._clahe,
        )
        self._register(
            OperatorSpec(
                "hist_match",
                "灰度匹配",
                "直方图",
                "按目标均值和标准差进行商业流程常用的灰度匹配。",
                (
                    p("target_mean", "目标均值", "float", 128.0, 0.0, 255.0, 1.0),
                    p("target_std", "目标标准差", "float", 45.0, 1.0, 128.0, 1.0),
                ),
                supports_multiband=True,
            ),
            self._hist_match_stats,
        )
        self._register(
            OperatorSpec(
                "hist_match_reference",
                "参考影像直方图匹配",
                "直方图",
                "将当前影像直方图匹配到参考影像。",
                supports_multiband=True,
            ),
            self._hist_match_reference,
        )
        self._register(
            OperatorSpec(
                "mean_filter",
                "均值滤波",
                "空间滤波",
                "使用均值卷积核平滑噪声。",
                (p("ksize", "窗口大小", "odd", 3, 3, 31, 2),),
                supports_multiband=True,
            ),
            self._mean_filter,
        )
        self._register(
            OperatorSpec(
                "gaussian_filter",
                "高斯滤波",
                "空间滤波",
                "使用高斯核进行平滑。",
                (
                    p("ksize", "窗口大小", "odd", 5, 3, 51, 2),
                    p("sigma", "Sigma", "float", 1.0, 0.0, 10.0, 0.1),
                ),
                supports_multiband=True,
            ),
            self._gaussian_filter,
        )
        self._register(
            OperatorSpec(
                "median_filter",
                "中值滤波",
                "空间滤波",
                "对椒盐噪声鲁棒的中值平滑。",
                (p("ksize", "窗口大小", "odd", 3, 3, 31, 2),),
                supports_multiband=True,
            ),
            self._median_filter,
        )
        self._register(
            OperatorSpec(
                "bilateral_filter",
                "双边滤波",
                "空间滤波",
                "尽量保边的非线性平滑。",
                (
                    p("diameter", "邻域直径", "int", 7, 3, 21, 2),
                    p("sigma_color", "颜色 Sigma", "float", 50.0, 1.0, 200.0, 1.0),
                    p("sigma_space", "空间 Sigma", "float", 50.0, 1.0, 200.0, 1.0),
                ),
            ),
            self._bilateral_filter,
        )
        self._register(
            OperatorSpec(
                "unsharp",
                "反锐化增强",
                "锐化",
                "用模糊图差分增强边缘和纹理。",
                (
                    p("amount", "增强强度", "float", 1.5, 0.1, 5.0, 0.1),
                    p("ksize", "模糊窗口", "odd", 5, 3, 51, 2),
                ),
            ),
            self._unsharp,
        )
        self._register(
            OperatorSpec(
                "laplacian_sharpen",
                "Laplacian 锐化",
                "锐化",
                "使用二阶导数增强细节。",
                (p("amount", "增强强度", "float", 0.7, 0.1, 3.0, 0.1),),
            ),
            self._laplacian_sharpen,
        )
        self._register(
            OperatorSpec(
                "sobel_edges",
                "Sobel 边缘",
                "边缘与梯度",
                "计算 Sobel 梯度幅值。",
                (p("ksize", "窗口大小", "odd", 3, 3, 7, 2),),
                preview_hint="gradient",
            ),
            self._sobel_edges,
        )
        self._register(
            OperatorSpec(
                "scharr_edges",
                "Scharr 边缘",
                "边缘与梯度",
                "计算 Scharr 梯度幅值，适合精细边缘。",
                preview_hint="gradient",
            ),
            self._scharr_edges,
        )
        self._register(
            OperatorSpec(
                "laplacian_edges",
                "Laplacian 边缘",
                "边缘与梯度",
                "二阶导数边缘检测。",
                (p("ksize", "窗口大小", "odd", 3, 1, 7, 2),),
                preview_hint="gradient",
            ),
            self._laplacian_edges,
        )
        self._register(
            OperatorSpec(
                "canny",
                "Canny 边缘",
                "边缘与梯度",
                "经典双阈值边缘提取。",
                (
                    p("threshold1", "低阈值", "float", 80.0, 0.0, 500.0, 1.0),
                    p("threshold2", "高阈值", "float", 160.0, 0.0, 500.0, 1.0),
                    p(
                        "aperture",
                        "孔径",
                        "choice",
                        "3",
                        options=("3", "5", "7"),
                        option_labels={
                            "3": "3x3(精细)",
                            "5": "5x5(均衡)",
                            "7": "7x7(平滑)",
                        },
                    ),
                ),
                preview_hint="mask",
                usage="Canny 使用低/高双阈值追踪边缘。高阈值控制强边缘，低阈值用于连接弱边缘。",
            ),
            self._canny,
        )
        self._register(
            OperatorSpec(
                "prewitt_edges",
                "Prewitt 边缘",
                "边缘与梯度",
                "使用 Prewitt 算子提取边缘。",
                preview_hint="gradient",
            ),
            self._prewitt_edges,
        )
        self._register(
            OperatorSpec(
                "gradient",
                "梯度计算",
                "边缘与梯度",
                "输出 X、Y、幅值或方向梯度。",
                (
                    p(
                        "mode",
                        "输出类型",
                        "choice",
                        "magnitude",
                        options=("magnitude", "x", "y", "direction"),
                        option_labels={
                            "magnitude": "Magnitude(梯度幅值)",
                            "x": "X(水平方向梯度)",
                            "y": "Y(垂直方向梯度)",
                            "direction": "Direction(梯度方向)",
                        },
                    ),
                    p("ksize", "窗口大小", "odd", 3, 3, 7, 2),
                ),
                preview_hint="gradient",
                usage="梯度幅值用于突出边缘强度；X/Y 分量用于方向性纹理分析；方向图用于观察边缘朝向。",
            ),
            self._gradient,
        )
        self._register(
            OperatorSpec(
                "morphology",
                "形态学处理",
                "形态学",
                "腐蚀、膨胀、开闭运算、顶帽、黑帽和形态学梯度。",
                (
                    p(
                        "operation",
                        "操作",
                        "choice",
                        "open",
                        options=(
                            "erode",
                            "dilate",
                            "open",
                            "close",
                            "gradient",
                            "tophat",
                            "blackhat",
                        ),
                        option_labels={
                            "erode": "Erode(腐蚀)",
                            "dilate": "Dilate(膨胀)",
                            "open": "Open(开运算)",
                            "close": "Close(闭运算)",
                            "gradient": "Gradient(形态学梯度)",
                            "tophat": "Tophat(顶帽)",
                            "blackhat": "Blackhat(黑帽)",
                        },
                    ),
                    p("ksize", "核大小", "odd", 3, 3, 31, 2),
                    p("iterations", "迭代次数", "int", 1, 1, 10, 1),
                ),
                usage="开运算常用于去小噪声，闭运算常用于填小孔洞，顶帽/黑帽适合增强亮/暗小目标。",
            ),
            self._morphology,
        )
        self._register(
            OperatorSpec(
                "threshold",
                "阈值分割",
                "分割",
                "固定阈值、Otsu 或自适应阈值分割。",
                (
                    p(
                        "method",
                        "方法",
                        "choice",
                        "otsu",
                        options=("binary", "otsu", "adaptive_mean", "adaptive_gaussian"),
                        option_labels={
                            "binary": "Binary(固定阈值)",
                            "otsu": "OTSU(大津法)",
                            "adaptive_mean": "Adaptive Mean(自适应均值)",
                            "adaptive_gaussian": "Adaptive Gaussian(自适应高斯)",
                        },
                    ),
                    p(
                        "threshold",
                        "阈值",
                        "float",
                        128.0,
                        0.0,
                        255.0,
                        1.0,
                        visible_when={"method": ("binary",)},
                        help_text="仅固定阈值模式需要手动输入。",
                    ),
                    p(
                        "block_size",
                        "块大小",
                        "odd",
                        15,
                        3,
                        99,
                        2,
                        visible_when={"method": ("adaptive_mean", "adaptive_gaussian")},
                        help_text="仅自适应阈值模式需要，必须为奇数。",
                    ),
                ),
                preview_hint="mask",
                usage=(
                    "Binary 需要手动阈值；OTSU(大津法)会自动计算最佳阈值，不需要手动输入；"
                    "自适应阈值按局部窗口计算阈值，适合光照不均匀图像。"
                ),
            ),
            self._threshold,
        )
        self._register(
            OperatorSpec(
                "pca",
                "PCA 主成分",
                "多波段变换",
                "对多波段/多通道影像进行 PCA，输出指定主成分。",
                (p("component", "主成分序号", "int", 1, 1, 8, 1),),
                supports_multiband=True,
                preview_hint="gradient",
            ),
            self._pca,
        )
        self._register(
            OperatorSpec(
                "ihs_intensity",
                "IHS 强度分量",
                "多波段变换",
                "提取 IHS/HSV 近似强度分量。",
                preview_hint="gradient",
            ),
            self._ihs_intensity,
        )
        self._register(
            OperatorSpec(
                "fft_filter",
                "FFT 频域滤波",
                "频域",
                "理想低通或高通频域滤波。",
                (
                    p(
                        "mode",
                        "模式",
                        "choice",
                        "lowpass",
                        options=("lowpass", "highpass"),
                        option_labels={
                            "lowpass": "Lowpass(低通)",
                            "highpass": "Highpass(高通)",
                        },
                    ),
                    p("radius", "半径", "float", 30.0, 1.0, 512.0, 1.0),
                ),
                preview_hint="gradient",
                usage="低通保留大尺度背景并抑制噪声；高通增强边缘、纹理和突变信息。",
            ),
            self._fft_filter,
        )
        self._register(
            OperatorSpec(
                "nd_index",
                "归一化差异指数",
                "多波段变换",
                "根据两个波段计算 (A-B)/(A+B)，可用于 NDVI/NDWI 类指数。",
                (
                    p("band_a", "波段 A", "int", 1, 1, 32, 1),
                    p("band_b", "波段 B", "int", 2, 1, 32, 1),
                ),
                supports_multiband=True,
                preview_hint="gradient",
            ),
            self._normalized_difference,
        )

    @staticmethod
    def display_image(image: np.ndarray) -> np.ndarray:
        arr = np.asarray(image)
        if arr.ndim == 2:
            return _stretch_to_uint8(arr)
        if arr.ndim == 3:
            if arr.shape[2] == 1:
                return _stretch_to_uint8(arr[:, :, 0])
            if arr.shape[2] >= 3:
                channels = [_stretch_to_uint8(arr[:, :, i]) for i in range(3)]
                return np.dstack(channels)
        return _stretch_to_uint8(arr)

    @staticmethod
    def to_display_rgb(image: np.ndarray) -> np.ndarray:
        display = ImageProcessingCore.display_image(image)
        if display.ndim == 2:
            return cv2.cvtColor(display, cv2.COLOR_GRAY2RGB)
        return display

    def _grayscale(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image)
        return ProcessingResult(gray, _basic_metrics(gray))

    def _color_space(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        target = str(params["target"]).upper()
        if target == "GRAY":
            return self._grayscale(image, params)
        rgb = _to_rgb_uint8(image)
        code = {
            "HSV": cv2.COLOR_RGB2HSV,
            "HLS": cv2.COLOR_RGB2HLS,
            "LAB": cv2.COLOR_RGB2Lab,
            "YCRCB": cv2.COLOR_RGB2YCrCb,
        }.get(target)
        if code is None:
            raise AlgorithmError(f"不支持的色彩空间: {target}")
        out = cv2.cvtColor(rgb, code)
        return ProcessingResult(out, _basic_metrics(out))

    def _linear_stretch(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        low = float(params["low_percent"])
        high = float(params["high_percent"])
        if high <= low:
            raise AlgorithmError("高截断百分比必须大于低截断百分比")
        out = _apply_per_band(image, lambda band: _percent_stretch(band, low, high))
        return ProcessingResult(out, _basic_metrics(out))

    def _std_stretch(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        sigma = float(params["sigma"])

        def stretch(band):
            arr = band.astype(np.float32)
            mean = float(np.nanmean(arr))
            std = float(np.nanstd(arr))
            if std <= 1e-8:
                return np.zeros_like(band, dtype=np.uint8)
            return _scale_between(arr, mean - sigma * std, mean + sigma * std)

        out = _apply_per_band(image, stretch)
        return ProcessingResult(out, _basic_metrics(out))

    def _gamma(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gamma = max(float(params["gamma"]), 1e-6)

        def correct(band):
            arr = _percent_stretch(band, 0, 100).astype(np.float32) / 255.0
            return np.clip(np.power(arr, 1.0 / gamma) * 255, 0, 255).astype(np.uint8)

        out = _apply_per_band(image, correct)
        return ProcessingResult(out, _basic_metrics(out))

    def _hist_equalization(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        rgb = _to_rgb_uint8(image)
        if _is_single_band(image):
            out = cv2.equalizeHist(_to_gray(image))
        else:
            ycrcb = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
            ycrcb[:, :, 0] = cv2.equalizeHist(ycrcb[:, :, 0])
            out = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)
        return ProcessingResult(out, _basic_metrics(out))

    def _clahe(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        clip = float(params["clip_limit"])
        tile = _odd_or_int(params["tile_size"], odd=False)
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
        rgb = _to_rgb_uint8(image)
        if _is_single_band(image):
            out = clahe.apply(_to_gray(image))
        else:
            lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab)
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            out = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)
        return ProcessingResult(out, _basic_metrics(out))

    def _hist_match_stats(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        target_mean = float(params["target_mean"])
        target_std = max(float(params["target_std"]), 1e-6)

        def match(band):
            arr = band.astype(np.float32)
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            if std <= 1e-8:
                return np.clip(np.full_like(arr, target_mean), 0, 255).astype(np.uint8)
            return np.clip((arr - mean) / std * target_std + target_mean, 0, 255).astype(np.uint8)

        out = _apply_per_band(image, match)
        return ProcessingResult(out, _basic_metrics(out))

    def _hist_match_reference(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        reference = params.get("reference_image")
        if reference is None:
            raise AlgorithmError("参考影像直方图匹配需要先加载参考影像")
        out = match_histogram(image, np.asarray(reference))
        return ProcessingResult(out, _basic_metrics(out))

    def _mean_filter(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        out = cv2.blur(image, (k, k))
        return ProcessingResult(out, _basic_metrics(out))

    def _gaussian_filter(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        sigma = float(params["sigma"])
        out = cv2.GaussianBlur(image, (k, k), sigma)
        return ProcessingResult(out, _basic_metrics(out))

    def _median_filter(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        source = _uint8_if_needed(image)
        out = cv2.medianBlur(source, k)
        return ProcessingResult(out, _basic_metrics(out))

    def _bilateral_filter(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        source = _to_rgb_uint8(image) if image.ndim == 3 else _to_gray(image)
        out = cv2.bilateralFilter(
            source,
            int(params["diameter"]),
            float(params["sigma_color"]),
            float(params["sigma_space"]),
        )
        return ProcessingResult(out, _basic_metrics(out))

    def _unsharp(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        amount = float(params["amount"])
        source = _uint8_if_needed(image)
        blur = cv2.GaussianBlur(source, (k, k), 0)
        out = cv2.addWeighted(source, 1.0 + amount, blur, -amount, 0)
        return ProcessingResult(out, _basic_metrics(out))

    def _laplacian_sharpen(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        amount = float(params["amount"])
        source = _uint8_if_needed(image)
        lap = cv2.Laplacian(source, cv2.CV_32F)
        out = np.clip(source.astype(np.float32) - amount * lap, 0, 255).astype(np.uint8)
        return ProcessingResult(out, _basic_metrics(out))

    def _sobel_edges(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        gray = _to_gray(image)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=k)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=k)
        mag = cv2.magnitude(gx, gy)
        out = _stretch_to_uint8(mag)
        return ProcessingResult(out, _basic_metrics(out))

    def _scharr_edges(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image)
        gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
        gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
        out = _stretch_to_uint8(cv2.magnitude(gx, gy))
        return ProcessingResult(out, _basic_metrics(out))

    def _laplacian_edges(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        k = _odd_or_int(params["ksize"])
        gray = _to_gray(image)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=k)
        out = _stretch_to_uint8(np.abs(lap))
        return ProcessingResult(out, _basic_metrics(out))

    def _canny(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image)
        out = cv2.Canny(
            gray,
            float(params["threshold1"]),
            float(params["threshold2"]),
            apertureSize=int(params["aperture"]),
        )
        return ProcessingResult(out, _basic_metrics(out))

    def _prewitt_edges(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image).astype(np.float32)
        kx = np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], dtype=np.float32)
        ky = np.array([[1, 1, 1], [0, 0, 0], [-1, -1, -1]], dtype=np.float32)
        gx = cv2.filter2D(gray, cv2.CV_32F, kx)
        gy = cv2.filter2D(gray, cv2.CV_32F, ky)
        out = _stretch_to_uint8(cv2.magnitude(gx, gy))
        return ProcessingResult(out, _basic_metrics(out))

    def _gradient(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        mode = str(params["mode"])
        k = _odd_or_int(params["ksize"])
        gray = _to_gray(image)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=k)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=k)
        if mode == "x":
            out = _stretch_to_uint8(np.abs(gx))
        elif mode == "y":
            out = _stretch_to_uint8(np.abs(gy))
        elif mode == "direction":
            _, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
            out = _stretch_to_uint8(angle)
        else:
            out = _stretch_to_uint8(cv2.magnitude(gx, gy))
        metrics = _basic_metrics(out)
        metrics["mode"] = mode
        return ProcessingResult(out, metrics)

    def _morphology(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        operation = str(params["operation"])
        k = _odd_or_int(params["ksize"])
        iterations = int(params["iterations"])
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        source = _uint8_if_needed(image)
        if operation == "erode":
            out = cv2.erode(source, kernel, iterations=iterations)
        elif operation == "dilate":
            out = cv2.dilate(source, kernel, iterations=iterations)
        else:
            op = {
                "open": cv2.MORPH_OPEN,
                "close": cv2.MORPH_CLOSE,
                "gradient": cv2.MORPH_GRADIENT,
                "tophat": cv2.MORPH_TOPHAT,
                "blackhat": cv2.MORPH_BLACKHAT,
            }[operation]
            out = cv2.morphologyEx(source, op, kernel, iterations=iterations)
        return ProcessingResult(out, _basic_metrics(out))

    def _threshold(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image)
        method = str(params["method"])
        if method == "otsu":
            value, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif method == "adaptive_mean":
            block = _odd_or_int(params["block_size"])
            out = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, 5
            )
            value = None
        elif method == "adaptive_gaussian":
            block = _odd_or_int(params["block_size"])
            out = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 5
            )
            value = None
        else:
            value = float(params["threshold"])
            _, out = cv2.threshold(gray, value, 255, cv2.THRESH_BINARY)
        metrics = _basic_metrics(out)
        if value is not None:
            metrics["threshold"] = float(value)
        return ProcessingResult(out, metrics)

    def _pca(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        arr = np.asarray(image)
        if arr.ndim == 2:
            return ProcessingResult(_stretch_to_uint8(arr), _basic_metrics(arr))
        h, w, bands = arr.shape
        component = int(params["component"]) - 1
        component = max(0, min(component, bands - 1))
        flat = arr.reshape(-1, bands).astype(np.float64)
        mean = np.mean(flat, axis=0)
        centered = flat - mean
        cov = np.zeros((bands, bands), dtype=np.float64)
        denom = max(len(centered) - 1, 1)
        for i in range(bands):
            for j in range(i, bands):
                value = float(np.sum(centered[:, i] * centered[:, j])) / denom
                cov[i, j] = value
                cov[j, i] = value

        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvals = np.maximum(eigvals[order], 0.0)
        eigvecs = eigvecs[:, order]
        selected = np.sum(centered * eigvecs[:, component], axis=1).reshape(h, w)
        explained = eigvals
        total = float(np.sum(explained)) or 1.0
        out = _stretch_to_uint8(selected)
        metrics = _basic_metrics(out)
        metrics["component"] = component + 1
        metrics["explained_ratio"] = float(explained[component] / total)
        return ProcessingResult(out, metrics)

    def _ihs_intensity(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        rgb = _to_rgb_uint8(image)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        out = hsv[:, :, 2]
        return ProcessingResult(out, _basic_metrics(out))

    def _fft_filter(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        gray = _to_gray(image).astype(np.float32)
        mode = str(params["mode"])
        radius = float(params["radius"])
        rows, cols = gray.shape
        crow, ccol = rows // 2, cols // 2
        y, x = np.ogrid[:rows, :cols]
        dist = np.sqrt((y - crow) ** 2 + (x - ccol) ** 2)
        mask = dist <= radius
        if mode == "highpass":
            mask = ~mask
        spectrum = np.fft.fftshift(np.fft.fft2(gray))
        filtered = np.fft.ifft2(np.fft.ifftshift(spectrum * mask))
        out = _stretch_to_uint8(np.abs(filtered))
        return ProcessingResult(out, _basic_metrics(out))

    def _normalized_difference(self, image: np.ndarray, params: Dict) -> ProcessingResult:
        arr = np.asarray(image)
        if arr.ndim < 3 or arr.shape[2] < 2:
            raise AlgorithmError("归一化差异指数需要至少两个波段")
        band_a = max(1, int(params["band_a"])) - 1
        band_b = max(1, int(params["band_b"])) - 1
        band_a = min(band_a, arr.shape[2] - 1)
        band_b = min(band_b, arr.shape[2] - 1)
        a = arr[:, :, band_a].astype(np.float32)
        b = arr[:, :, band_b].astype(np.float32)
        nd = (a - b) / (a + b + 1e-6)
        metrics = _basic_metrics(nd)
        metrics["range"] = (-1.0, 1.0)
        return ProcessingResult(nd.astype(np.float32), metrics, _stretch_to_uint8(nd))


def _is_single_band(image: np.ndarray) -> bool:
    return image.ndim == 2 or (image.ndim == 3 and image.shape[2] == 1)


def _to_gray(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 2:
        return _uint8_if_needed(arr)
    if arr.shape[2] == 1:
        return _uint8_if_needed(arr[:, :, 0])
    rgb = _to_rgb_uint8(arr)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _to_rgb_uint8(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 2:
        return cv2.cvtColor(_uint8_if_needed(arr), cv2.COLOR_GRAY2RGB)
    if arr.shape[2] == 1:
        return cv2.cvtColor(_uint8_if_needed(arr[:, :, 0]), cv2.COLOR_GRAY2RGB)
    if arr.shape[2] >= 3:
        return _uint8_if_needed(arr[:, :, :3])
    return cv2.cvtColor(_uint8_if_needed(arr[:, :, 0]), cv2.COLOR_GRAY2RGB)


def _uint8_if_needed(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.dtype == np.uint8:
        return np.ascontiguousarray(arr)
    return _apply_per_band(arr, lambda band: _stretch_to_uint8(band))


def _apply_per_band(image: np.ndarray, func: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 2:
        return func(arr)
    bands = [func(arr[:, :, i]) for i in range(arr.shape[2])]
    return np.dstack(bands)


def _percent_stretch(band: np.ndarray, low_percent: float, high_percent: float) -> np.ndarray:
    arr = band.astype(np.float32)
    low = float(np.nanpercentile(arr, low_percent))
    high = float(np.nanpercentile(arr, high_percent))
    return _scale_between(arr, low, high)


def _stretch_to_uint8(band: np.ndarray) -> np.ndarray:
    arr = np.asarray(band).astype(np.float32)
    low = float(np.nanmin(arr))
    high = float(np.nanmax(arr))
    return _scale_between(arr, low, high)


def _scale_between(arr: np.ndarray, low: float, high: float) -> np.ndarray:
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros(arr.shape, dtype=np.uint8)
    scaled = (arr.astype(np.float32) - low) / (high - low)
    return np.clip(scaled * 255.0, 0, 255).astype(np.uint8)


def _odd_or_int(value: Any, odd: bool = True) -> int:
    k = int(round(float(value)))
    if odd and k % 2 == 0:
        k += 1
    return max(k, 1)


def _basic_metrics(image: np.ndarray) -> Dict[str, Any]:
    arr = np.asarray(image)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"min": None, "max": None, "mean": None, "std": None}
    return {
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
    }


def match_histogram(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Match source histogram to a reference image per band."""
    src = np.asarray(source)
    ref = np.asarray(reference)
    if src.ndim != ref.ndim:
        raise AlgorithmError("源影像和参考影像维度不一致")
    if src.ndim == 2:
        return _match_histogram_band(src, ref)
    bands = min(src.shape[2], ref.shape[2])
    out = src.copy()
    for i in range(bands):
        out[:, :, i] = _match_histogram_band(src[:, :, i], ref[:, :, i])
    return out


def _match_histogram_band(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    src_u8 = _stretch_to_uint8(source)
    ref_u8 = _stretch_to_uint8(reference)
    src_values, src_idx, src_counts = np.unique(
        src_u8.ravel(), return_inverse=True, return_counts=True
    )
    ref_values, ref_counts = np.unique(ref_u8.ravel(), return_counts=True)
    src_quantiles = np.cumsum(src_counts).astype(np.float64)
    src_quantiles /= src_quantiles[-1]
    ref_quantiles = np.cumsum(ref_counts).astype(np.float64)
    ref_quantiles /= ref_quantiles[-1]
    interp = np.interp(src_quantiles, ref_quantiles, ref_values)
    return interp[src_idx].reshape(src_u8.shape).astype(np.uint8)


def operator_choices() -> List[str]:
    return [spec.id for spec in ImageProcessingCore().list_operators()]


def summarize_specs(specs: Iterable[OperatorSpec]) -> Dict[str, List[Dict[str, Any]]]:
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for spec in specs:
        payload.setdefault(spec.category, []).append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "parameters": [param.__dict__ for param in spec.parameters],
            }
        )
    return payload
