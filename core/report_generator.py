"""报告生成器 — 一键导出 HTML/PDF 精度报告"""
import base64
import io
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common.logger import logger

# 中文字体配置
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


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
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

        # 直方图: 匹配分数分布
        if stats.scores:
            ax1.hist(stats.scores, bins=20, color="#6366f1", edgecolor="white", alpha=0.85)
            ax1.axvline(stats.mean_score, color="#ef4444", linestyle="--", label=f'均值={stats.mean_score:.3f}')
            ax1.set_title("匹配分数分布")
            ax1.set_xlabel("相关系数")
            ax1.set_ylabel("频数")
            ax1.legend()

            # 饼图: 成功率
            labels = ["成功", "失败"]
            sizes = [stats.successful_pairs, stats.total_pairs - stats.successful_pairs]
            colors = ["#22c55e", "#ef4444"]
            ax2.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90)
            ax2.set_title(f"成功率: {stats.successful_pairs}/{stats.total_pairs}")
        else:
            ax1.text(0.5, 0.5, "无数据", ha="center", va="center", fontsize=14)
            ax2.text(0.5, 0.5, "无数据", ha="center", va="center", fontsize=14)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        charts["match_distribution"] = base64.b64encode(buf.getvalue()).decode()
        return charts

    def _build_feature_charts(self, stats: FeatureStats) -> Dict[str, str]:
        charts = {}
        fig, ax = plt.subplots(figsize=(10, 5))

        if stats.feature_counts:
            indices = range(len(stats.feature_counts))
            ax.bar(indices, stats.feature_counts, color="#6366f1", alpha=0.85)
            ax.axhline(stats.mean_features, color="#ef4444", linestyle="--",
                      label=f"均值={stats.mean_features:.0f}")
            ax.set_title("特征点数量分布")
            ax.set_xlabel("影像序号")
            ax.set_ylabel("特征点数量")
            ax.legend()

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        charts["feature_distribution"] = base64.b64encode(buf.getvalue()).decode()
        return charts

    def _build_html(self, title: str, subtitle: str, stats, charts: Dict[str, str],
                    extra_info: Dict[str, str] = None) -> str:
        """构建带图表的 HTML 报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        chart_html = ""
        for name, b64 in charts.items():
            chart_html += f'<div class="chart"><img src="data:image/png;base64,{b64}" /></div>\n'

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
                extra_html += f"<tr><td>{k}</td><td>{v}</td></tr>"
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
