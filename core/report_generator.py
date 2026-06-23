"""报告生成器 — 一键导出 HTML/PDF 精度报告"""

import base64
import html
import io
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from common.logger import logger


@dataclass
class MatchStats:
    """匹配精度统计"""

    total_pairs: int = 0
    successful_pairs: int = 0
    mean_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 0.0
    std_score: float = 0.0
    scores: List[float] = field(default_factory=list)
    thresholds: Dict[str, int] = field(default_factory=dict)

    def compute(self):
        if self.scores:
            arr = np.array(self.scores)
            self.mean_score = float(np.mean(arr))
            self.max_score = float(np.max(arr))
            self.min_score = float(np.min(arr))
            self.std_score = float(np.std(arr))
            for t in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
                self.thresholds[f">{t}"] = int(np.sum(arr > t))


@dataclass
class FeatureStats:
    """特征检测统计"""

    image_count: int = 0
    total_features: int = 0
    mean_features: float = 0.0
    max_features: int = 0
    min_features: int = 0
    feature_counts: List[int] = field(default_factory=list)

    def compute(self):
        if self.feature_counts:
            arr = np.array(self.feature_counts)
            self.total_features = int(np.sum(arr))
            self.mean_features = float(np.mean(arr))
            self.max_features = int(np.max(arr))
            self.min_features = int(np.min(arr))


class ReportGenerator:
    """报告生成器"""

    def __init__(self, output_dir: str = ""):
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.charts: Dict[str, str] = {}  # chart_name -> base64 PNG

    def generate_match_report(
        self,
        title: str,
        stats: MatchStats,
        extra_info: Dict[str, str] = None,
        output_path: str = "",
    ) -> str:
        """生成匹配精度报告"""
        charts = self._build_match_charts(stats)
        html = self._build_html(title, "影像匹配精度报告", stats, charts, extra_info)
        return self._save(html, output_path or f"match_report_{int(time.time())}.html")

    def generate_feature_report(
        self,
        title: str,
        stats: FeatureStats,
        extra_info: Dict[str, str] = None,
        output_path: str = "",
    ) -> str:
        """生成特征检测报告"""
        charts = self._build_feature_charts(stats)
        html = self._build_html(title, "特征检测报告", stats, charts, extra_info)
        return self._save(html, output_path or f"feature_report_{int(time.time())}.html")

    def _build_match_charts(self, stats: MatchStats) -> Dict[str, str]:
        charts = {}
        if stats.scores:
            counts, edges = np.histogram(np.asarray(stats.scores, dtype=np.float64), bins=20)
            bars = [
                (f"{edges[i]:.2f}-{edges[i + 1]:.2f}", int(counts[i])) for i in range(len(counts))
            ]
            charts["match_distribution"] = self._encode_svg(
                self._bar_svg("匹配分数分布", bars, "相关系数区间", "频数")
            )
            failed = max(0, stats.total_pairs - stats.successful_pairs)
            charts["match_success"] = self._encode_svg(
                self._bar_svg(
                    f"成功率: {stats.successful_pairs}/{stats.total_pairs}",
                    [("成功", stats.successful_pairs), ("失败", failed)],
                    "状态",
                    "数量",
                    colors=["#22c55e", "#ef4444"],
                )
            )
        else:
            charts["match_distribution"] = self._encode_svg(self._empty_svg("匹配分数分布"))
        return charts

    def _build_feature_charts(self, stats: FeatureStats) -> Dict[str, str]:
        charts = {}
        if stats.feature_counts:
            bars = [(str(i + 1), int(count)) for i, count in enumerate(stats.feature_counts)]
            charts["feature_distribution"] = self._encode_svg(
                self._bar_svg("特征点数量分布", bars, "影像序号", "特征点数量")
            )
        else:
            charts["feature_distribution"] = self._encode_svg(self._empty_svg("特征点数量分布"))
        return charts

    @staticmethod
    def _encode_svg(svg: str) -> str:
        return base64.b64encode(svg.encode("utf-8")).decode("ascii")

    @staticmethod
    def _empty_svg(title: str) -> str:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="320" viewBox="0 0 960 320">
<rect width="960" height="320" fill="#151827"/>
<text x="40" y="48" fill="#e2e4e9" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="22">{html.escape(title)}</text>
<text x="480" y="170" fill="#8b8fa3" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="18" text-anchor="middle">无数据</text>
</svg>"""

    @staticmethod
    def _bar_svg(
        title: str,
        bars: List[Tuple[str, int]],
        x_label: str,
        y_label: str,
        colors: Optional[List[str]] = None,
    ) -> str:
        width, height = 960, 360
        left, right, top, bottom = 70, 30, 62, 58
        plot_w = width - left - right
        plot_h = height - top - bottom
        max_value = max((value for _, value in bars), default=1) or 1
        gap = 8
        bar_w = max(4, (plot_w - gap * max(0, len(bars) - 1)) / max(1, len(bars)))
        colors = colors or ["#6366f1"] * len(bars)

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect width="{width}" height="{height}" fill="#151827"/>',
            f'<text x="{left}" y="38" fill="#e2e4e9" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="22">{html.escape(title)}</text>',
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#34384a"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#34384a"/>',
        ]
        for tick in range(5):
            value = max_value * tick / 4
            y = top + plot_h - plot_h * tick / 4
            parts.append(
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#252836"/>'
            )
            parts.append(
                f'<text x="{left - 10}" y="{y + 4:.1f}" fill="#8b8fa3" font-family="Segoe UI,sans-serif" font-size="11" text-anchor="end">{value:.0f}</text>'
            )
        for i, (label, value) in enumerate(bars):
            x = left + i * (bar_w + gap)
            h = plot_h * value / max_value
            y = top + plot_h - h
            color = colors[i % len(colors)]
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="2"/>'
            )
            if len(bars) <= 12 or i % max(1, len(bars) // 10) == 0:
                parts.append(
                    f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 18}" fill="#8b8fa3" font-family="Segoe UI,sans-serif" font-size="10" text-anchor="middle">{html.escape(label)}</text>'
                )
        parts.append(
            f'<text x="{left + plot_w / 2}" y="{height - 14}" fill="#8b8fa3" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="13" text-anchor="middle">{html.escape(x_label)}</text>'
        )
        parts.append(
            f'<text x="18" y="{top + plot_h / 2}" fill="#8b8fa3" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="13" text-anchor="middle" transform="rotate(-90 18 {top + plot_h / 2})">{html.escape(y_label)}</text>'
        )
        parts.append("</svg>")
        return "\n".join(parts)

    def _build_html(
        self,
        title: str,
        subtitle: str,
        stats,
        charts: Dict[str, str],
        extra_info: Dict[str, str] = None,
    ) -> str:
        """构建带图表的 HTML 报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        chart_html = ""
        for name, b64 in charts.items():
            chart_html += f'<div class="chart"><img src="data:image/svg+xml;base64,{b64}" alt="{html.escape(name)}" /></div>\n'

        # 统计表格
        stat_rows = []
        if isinstance(stats, MatchStats):
            stat_rows = [
                ("匹配总数", str(stats.total_pairs)),
                ("成功数", str(stats.successful_pairs)),
                ("平均相关系数", f"{stats.mean_score:.4f}"),
                ("最大相关系数", f"{stats.max_score:.4f}"),
                ("最小相关系数", f"{stats.min_score:.4f}"),
                ("标准差", f"{stats.std_score:.4f}"),
            ]
        elif isinstance(stats, FeatureStats):
            stat_rows = [
                ("影像数量", str(stats.image_count)),
                ("总特征点数", str(stats.total_features)),
                ("平均特征点", f"{stats.mean_features:.1f}"),
                ("最多特征点", str(stats.max_features)),
                ("最少特征点", str(stats.min_features)),
            ]

        stat_table = "<table><tr><th>指标</th><th>数值</th></tr>"
        for k, v in stat_rows:
            stat_table += f"<tr><td>{k}</td><td>{v}</td></tr>"
        stat_table += "</table>"

        # 额外信息
        extra_html = ""
        if extra_info:
            extra_html = '<div class="extra"><h3>附加信息</h3><table>'
            for k, v in extra_info.items():
                extra_html += (
                    f"<tr><td>{html.escape(str(k))}</td>"
                    f"<td>{self._format_extra_value(v)}</td></tr>"
                )
            extra_html += "</table></div>"

        return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; background: #0f1117; color: #e2e4e9; padding: 40px; }}
.header {{ text-align: center; padding: 30px 0; border-bottom: 2px solid #6366f1; margin-bottom: 30px; }}
.header h1 {{ color: #6366f1; font-size: 28px; }}
.header p {{ color: #8b8fa3; margin-top: 8px; }}
.stats {{ background: #1c1f2e; border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
.stats h2 {{ color: #6366f1; font-size: 18px; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #252836; }}
th {{ color: #8b8fa3; font-weight: 600; }}
.chart {{ background: #1c1f2e; border-radius: 10px; padding: 16px; margin-bottom: 20px; text-align: center; }}
.chart img {{ max-width: 100%; height: auto; }}
.extra {{ background: #1c1f2e; border-radius: 10px; padding: 20px; margin-bottom: 20px; }}
.extra h3 {{ color: #6366f1; font-size: 16px; margin-bottom: 10px; }}
.footer {{ text-align: center; color: #5b5f72; font-size: 12px; margin-top: 30px; padding-top: 16px; border-top: 1px solid #252836; }}
</style>
</head>
<body>
<div class="header">
<h1>{title}</h1>
<p>{subtitle} — 生成于 {now}</p>
</div>
<div class="stats"><h2>统计摘要</h2>{stat_table}</div>
{extra_html}
{chart_html}
<div class="footer">RSTao-Tool Report Generator &copy; {datetime.now().year}</div>
</body>
</html>"""

    def _save(self, html: str, filename: str) -> str:
        path = self.output_dir / filename
        path.write_text(html, encoding="utf-8")
        logger.info(f"报告已保存: {path}")
        return str(path)

    @staticmethod
    def _format_extra_value(value) -> str:
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = str(value)
        return html.escape(text).replace("\n", "<br>")
