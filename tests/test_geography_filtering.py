# coding=utf-8

from __future__ import annotations

import unittest
from pathlib import Path

from trendradar.core.frequency import load_frequency_words, matches_word_groups
from trendradar.report.geography_weekly import classify_title


KEYWORD_PATH = Path("config/custom/keyword/high_school_geography.txt")


class GeographyFilteringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.word_groups, cls.filter_words, cls.global_filters = load_frequency_words(str(KEYWORD_PATH))

    def matches_keyword_profile(self, title: str) -> bool:
        return matches_word_groups(title, self.word_groups, self.filter_words, self.global_filters)

    def test_market_cooling_title_is_not_geography(self) -> None:
        title = "AI交易降温，纳指跌超1%，博通大跌14%，金涨油跌，比特币承压"

        self.assertFalse(self.matches_keyword_profile(title))
        rule, terms = classify_title(title)
        self.assertIsNone(rule)
        self.assertEqual([], terms)

    def test_weather_cooling_still_matches_natural_geography(self) -> None:
        title = "冷空气影响北方，多地气温降温明显"

        self.assertTrue(self.matches_keyword_profile(title))
        rule, terms = classify_title(title)
        self.assertIsNotNone(rule)
        self.assertIn("降温", terms)

    def test_ai_industry_layout_matches_industrial_geography(self) -> None:
        title = "长三角加快AI产业布局，多地建设算力中心"

        self.assertTrue(self.matches_keyword_profile(title))
        rule, terms = classify_title(title)
        self.assertIsNotNone(rule)
        self.assertEqual("P1-必修地理2-人口城市产业", rule.name)
        self.assertIn("AI产业", terms)
        self.assertIn("算力中心", terms)

    def test_artificial_intelligence_industry_cluster_matches(self) -> None:
        title = "多地数据中心建设带动人工智能产业集群发展"

        self.assertTrue(self.matches_keyword_profile(title))
        rule, terms = classify_title(title)
        self.assertIsNotNone(rule)
        self.assertEqual("P1-必修地理2-人口城市产业", rule.name)
        self.assertIn("人工智能产业", terms)
        self.assertIn("数据中心", terms)


if __name__ == "__main__":
    unittest.main()
