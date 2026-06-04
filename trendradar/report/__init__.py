# coding=utf-8
"""
报告生成模块

提供报告生成和格式化功能，包括：
- HTML 报告生成
- 标题格式化工具

模块结构：
- helpers: 报告辅助函数（清理、转义、格式化）
- formatter: 平台标题格式化
- html: HTML 报告渲染
- generator: 报告生成器
"""

__all__ = [
    # 辅助函数
    "clean_title",
    "html_escape",
    "format_rank_display",
    # 格式化函数
    "format_title_for_platform",
    # HTML 渲染
    "render_html_content",
    # 报告生成器
    "prepare_report_data",
    "generate_html_report",
]


def __getattr__(name):
    if name in {"clean_title", "html_escape", "format_rank_display"}:
        from trendradar.report import helpers

        return getattr(helpers, name)
    if name == "format_title_for_platform":
        from trendradar.report.formatter import format_title_for_platform

        return format_title_for_platform
    if name == "render_html_content":
        from trendradar.report.html import render_html_content

        return render_html_content
    if name in {"prepare_report_data", "generate_html_report"}:
        from trendradar.report import generator

        return getattr(generator, name)
    raise AttributeError(f"module 'trendradar.report' has no attribute {name!r}")
