# coding=utf-8

from __future__ import annotations

import unittest

from trendradar.report.email_geography_weekly import build_summary_html, build_summary_lines, group_report_items


class GeographyEmailSummaryTest(unittest.TestCase):
    def sample_payload(self) -> dict:
        return {
            "start_date": "2026-06-04",
            "end_date": "2026-06-10",
            "total_candidates": 56,
            "selected_count": 2,
            "data_coverage": {
                "expected_dates": ["2026-06-04", "2026-06-05"],
                "database_dates": ["2026-06-04", "2026-06-05"],
                "total_news_records": 512,
                "platform_count": 11,
                "total_snapshots": 2,
            },
            "items": [
                {
                    "topic": "物流业景气指数重回扩张区间",
                    "topic_group": "P1-人口城市产业",
                    "platforms": ["抖音"],
                    "evidence": "1个平台；最高排名 3；累计抓取 1 次；2026-06-04 至 2026-06-04",
                    "original_urls": ["https://example.com/logistics"],
                },
                {
                    "topic": "中央气象台继续发布暴雨橙色预警",
                    "topic_group": "P1-自然灾害与天气气候",
                    "platforms": ["今日头条"],
                    "evidence": "1个平台；最高排名 29；累计抓取 1 次；2026-06-08 至 2026-06-08",
                    "original_urls": ["https://example.com/weather"],
                },
            ],
        }

    def test_groups_keep_report_order(self) -> None:
        groups = group_report_items(self.sample_payload()["items"])

        self.assertEqual("P1-人口城市产业", groups[0][0])
        self.assertEqual("P1-自然灾害与天气气候", groups[1][0])

    def test_plain_summary_contains_grouped_items(self) -> None:
        text = "\n".join(build_summary_lines(self.sample_payload()))

        self.assertIn("数据覆盖：2/2 天；512 条热榜记录；11 个平台；2 次快照", text)
        self.assertIn("P1-人口城市产业  1 条", text)
        self.assertIn("[抖音 排名3] 物流业景气指数重回扩张区间", text)
        self.assertIn("P1-自然灾害与天气气候  1 条", text)

    def test_html_summary_contains_links_and_groups(self) -> None:
        html = build_summary_html(self.sample_payload())

        self.assertIn("高中地理热点周报摘要", html)
        self.assertIn("P1-人口城市产业", html)
        self.assertIn("https://example.com/logistics", html)
        self.assertIn("中央气象台继续发布暴雨橙色预警", html)


if __name__ == "__main__":
    unittest.main()
