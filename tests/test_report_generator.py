"""报告生成器测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.report_generator import FeatureStats, MatchStats, ReportGenerator


class TestMatchStats:
    def test_defaults(self):
        s = MatchStats()
        assert s.total_pairs == 0
        assert s.successful_pairs == 0

    def test_compute_with_scores(self):
        s = MatchStats()
        s.scores = [0.5, 0.6, 0.7, 0.8, 0.9]
        s.total_pairs = len(s.scores)
        s.successful_pairs = 3
        s.compute()
        assert s.mean_score > 0
        assert s.max_score == 0.9
        assert s.min_score == 0.5

    def test_compute_empty(self):
        s = MatchStats()
        s.compute()
        assert s.mean_score == 0.0

    def test_thresholds(self):
        s = MatchStats()
        s.scores = [0.3, 0.55, 0.75, 0.85, 0.95]
        s.compute()
        assert s.thresholds[">0.5"] >= 3
        assert s.thresholds[">0.9"] >= 1


class TestFeatureStats:
    def test_defaults(self):
        s = FeatureStats()
        assert s.image_count == 0
        assert s.total_features == 0

    def test_compute(self):
        s = FeatureStats()
        s.feature_counts = [100, 200, 150, 50]
        s.image_count = 4
        s.compute()
        assert s.total_features == 500
        assert s.mean_features == 125.0
        assert s.max_features == 200
        assert s.min_features == 50


class TestReportGenerator:
    def test_init(self):
        rg = ReportGenerator(output_dir="./test_reports")
        assert rg.output_dir.name == "test_reports"

    def test_generate_match_report(self, tmp_path):
        rg = ReportGenerator(output_dir=str(tmp_path))
        stats = MatchStats()
        stats.scores = [0.75, 0.85, 0.65]
        stats.total_pairs = 3
        stats.successful_pairs = 3
        stats.compute()
        path = rg.generate_match_report("Test Report", stats, {}, str(tmp_path / "report.html"))
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "Test Report" in content
        assert "RSTao-Tool" in content

    def test_generate_feature_report(self, tmp_path):
        rg = ReportGenerator(output_dir=str(tmp_path))
        stats = FeatureStats()
        stats.feature_counts = [100, 300]
        stats.image_count = 2
        stats.compute()
        path = rg.generate_feature_report("Feature Report", stats, {}, str(tmp_path / "feat.html"))
        assert Path(path).exists()
