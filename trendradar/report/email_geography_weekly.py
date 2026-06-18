# coding=utf-8
"""
Email the latest high school geography weekly report as file attachments.

The script is intentionally standard-library only so it can run in GitHub
Actions after report generation without adding dependencies.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape as html_escape
from pathlib import Path


SMTP_CONFIGS = {
    "qq.com": ("smtp.qq.com", 465, "ssl"),
    "163.com": ("smtp.163.com", 465, "ssl"),
    "126.com": ("smtp.126.com", 465, "ssl"),
    "sina.com": ("smtp.sina.com", 465, "ssl"),
    "gmail.com": ("smtp.gmail.com", 587, "tls"),
    "outlook.com": ("smtp-mail.outlook.com", 587, "tls"),
    "hotmail.com": ("smtp-mail.outlook.com", 587, "tls"),
    "live.com": ("smtp-mail.outlook.com", 587, "tls"),
}
WEATHER_DISASTER_TERMS = {
    "暴雨", "强降雨", "洪水", "洪涝", "内涝", "台风", "寒潮", "冷空气", "高温",
    "热浪", "气温", "升温", "降温", "融化", "冰雪", "干旱", "沙尘", "沙尘暴",
    "雷暴", "冰雹", "龙卷风", "山火", "森林火灾", "地震", "余震", "滑坡",
    "泥石流", "崩塌", "海啸", "气象", "预警",
}


def find_latest_report(report_dir: Path) -> tuple[Path, Path | None]:
    markdown_reports = sorted(
        report_dir.glob("*-weekly-geography.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not markdown_reports:
        raise FileNotFoundError(f"No weekly geography Markdown report found in {report_dir}")

    md_path = markdown_reports[0]
    json_path = md_path.with_suffix(".json")
    return md_path, json_path if json_path.exists() else None


def resolve_smtp(from_email: str, smtp_server: str = "", smtp_port: str = "") -> tuple[str, int, str]:
    if smtp_server:
        port = int(smtp_port or "587")
        mode = "ssl" if port == 465 else "tls"
        return smtp_server, port, mode

    domain = from_email.split("@")[-1].lower()
    if domain in SMTP_CONFIGS:
        return SMTP_CONFIGS[domain]

    return f"smtp.{domain}", int(smtp_port or "587"), "tls"


def attach_file(message: EmailMessage, path: Path) -> None:
    content_type, _ = mimetypes.guess_type(str(path))
    if not content_type:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)
    message.add_attachment(
        path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=path.name,
    )


def build_run_url() -> str:
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if repository and run_id:
        return f"{server_url}/{repository}/actions/runs/{run_id}"
    return ""


def load_report_payload(json_path: Path | None) -> dict:
    if not json_path or not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[geography-email] Skip summary payload: {exc}")
        return {}


def infer_topic_group(item: dict) -> str:
    explicit_group = str(item.get("topic_group") or "").strip()
    if explicit_group:
        return explicit_group

    priority = str(item.get("priority") or "P?").strip()
    module = str(item.get("curriculum_module") or "")
    matched_terms = {str(term) for term in item.get("matched_terms") or []}
    if priority == "P1" and "地理2" in module:
        return "P1-人口城市产业"
    if priority == "P1":
        if matched_terms.intersection(WEATHER_DISASTER_TERMS):
            return "P1-自然灾害与天气气候"
        return "P1-地貌水文生态"
    if priority == "P2" and "区域发展" in module:
        return "P2-区域发展"
    if priority == "P2" and "资源" in module:
        return "P2-资源环境与国家安全"
    if priority == "P2":
        return "P2-自然地理基础"
    if priority == "P3":
        return "P3-地理技术与选修"
    return "其他候选"


def group_report_items(items: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in items:
        group = infer_topic_group(item)
        if group not in grouped:
            grouped[group] = []
            order.append(group)
        grouped[group].append(item)
    return [(group, grouped[group]) for group in order]


def extract_best_rank(evidence: str) -> str:
    match = re.search(r"最高排名\s*(\d+)", evidence or "")
    return match.group(1) if match else ""


def first_platform(item: dict) -> str:
    platforms = item.get("platforms") or []
    if platforms:
        return str(platforms[0])
    return "未知来源"


def first_url(item: dict) -> str:
    urls = item.get("original_urls") or []
    return str(urls[0]) if urls else ""


def build_summary_lines(payload: dict, max_items: int = 15) -> list[str]:
    items = list(payload.get("items") or [])[:max_items]
    if not items:
        return ["本期未生成可展示的候选热点摘要，请查看附件。"]

    lines: list[str] = []
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if start_date and end_date:
        lines.append(f"周期：{start_date} 至 {end_date}")
    lines.append(
        f"候选池：{payload.get('total_candidates', '未知')} 条；"
        f"入选候选：{payload.get('selected_count', len(items))} 条"
    )

    coverage = payload.get("data_coverage") or {}
    if coverage:
        lines.append(
            "数据覆盖："
            f"{len(coverage.get('database_dates') or [])}/{len(coverage.get('expected_dates') or [])} 天；"
            f"{coverage.get('total_news_records', '未知')} 条热榜记录；"
            f"{coverage.get('platform_count', '未知')} 个平台；"
            f"{coverage.get('total_snapshots', '未知')} 次快照"
        )

    for group, group_items in group_report_items(items):
        lines.append("")
        lines.append(f"{group}  {len(group_items)} 条")
        for idx, item in enumerate(group_items, start=1):
            rank = extract_best_rank(str(item.get("evidence") or ""))
            rank_text = f" 排名{rank}" if rank else ""
            lines.append(f"{idx}. [{first_platform(item)}{rank_text}] {item.get('topic', '')}")
    lines.extend(["", "完整切入角度、原始链接和权威核验入口见附件。"])
    return lines


def build_summary_html(payload: dict, max_items: int = 15) -> str:
    items = list(payload.get("items") or [])[:max_items]
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    coverage = payload.get("data_coverage") or {}

    meta_parts = []
    if start_date and end_date:
        meta_parts.append(f"{html_escape(str(start_date))} 至 {html_escape(str(end_date))}")
    meta_parts.append(
        f"候选池 {html_escape(str(payload.get('total_candidates', '未知')))} 条，"
        f"入选 {html_escape(str(payload.get('selected_count', len(items))))} 条"
    )
    if coverage:
        meta_parts.append(
            f"{len(coverage.get('database_dates') or [])}/{len(coverage.get('expected_dates') or [])} 天，"
            f"{html_escape(str(coverage.get('total_news_records', '未知')))} 条热榜记录，"
            f"{html_escape(str(coverage.get('platform_count', '未知')))} 个平台"
        )

    group_blocks: list[str] = []
    if items:
        for group, group_items in group_report_items(items):
            rows = []
            for idx, item in enumerate(group_items, start=1):
                topic = html_escape(str(item.get("topic") or ""))
                platform = html_escape(first_platform(item))
                rank = extract_best_rank(str(item.get("evidence") or ""))
                rank_badge = (
                    f'<span style="display:inline-block;background:#7a8596;color:#fff;border-radius:9px;'
                    f'padding:1px 7px;font-size:11px;font-weight:700;margin-left:5px;">{html_escape(rank)}</span>'
                    if rank
                    else ""
                )
                url = first_url(item)
                topic_html = (
                    f'<a href="{html_escape(url)}" style="color:#1664ff;text-decoration:none;">{topic}</a>'
                    if url
                    else f'<span style="color:#1664ff;">{topic}</span>'
                )
                rows.append(
                    f"""
                    <tr>
                      <td style="width:30px;vertical-align:top;padding:12px 0;">
                        <span style="display:inline-block;width:22px;height:22px;line-height:22px;border-radius:50%;
                        background:#f1f3f5;color:#8a94a6;text-align:center;font-size:12px;">{idx}</span>
                      </td>
                      <td style="padding:12px 0;border-bottom:1px solid #eef0f3;">
                        <div style="font-size:12px;color:#667085;margin-bottom:5px;">{platform}{rank_badge}</div>
                        <div style="font-size:14px;line-height:1.45;">{topic_html}</div>
                      </td>
                      <td style="width:48px;text-align:right;vertical-align:top;padding:12px 0;border-bottom:1px solid #eef0f3;">
                        <span style="display:inline-block;background:#ffb000;color:#7a4a00;border-radius:5px;
                        padding:2px 7px;font-size:10px;font-weight:700;">候选</span>
                      </td>
                    </tr>
                    """
                )
            group_blocks.append(
                f"""
                <section style="margin-top:22px;">
                  <div style="display:flex;align-items:baseline;border-bottom:1px solid #e7e9ee;padding-bottom:10px;">
                    <h2 style="font-size:18px;line-height:1.3;margin:0;color:#111827;">{html_escape(group)}
                      <span style="font-size:13px;color:#e5484d;margin-left:6px;">{len(group_items)} 条</span>
                    </h2>
                  </div>
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                    {''.join(rows)}
                  </table>
                </section>
                """
            )
    else:
        group_blocks.append(
            '<p style="color:#475467;font-size:14px;">本期未生成可展示的候选热点摘要，请查看附件。</p>'
        )

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;color:#101828;">
    <div style="max-width:720px;margin:0 auto;padding:24px 16px;">
      <div style="background:#ffffff;border:1px solid #e6e8ee;border-radius:8px;padding:22px;">
        <h1 style="font-size:22px;line-height:1.3;margin:0 0 10px;color:#101828;">高中地理热点周报摘要</h1>
        <p style="font-size:13px;line-height:1.7;color:#667085;margin:0 0 12px;">{'；'.join(meta_parts)}</p>
        <p style="font-size:13px;line-height:1.7;color:#667085;margin:0;">
          邮件正文展示候选摘要；Markdown 周报和 JSON 结构化数据仍在附件中。正式备课或发布前，请打开原始链接和权威核验入口复核具体事实。
        </p>
        {''.join(group_blocks)}
      </div>
    </div>
  </body>
</html>"""


def send_email(
    from_email: str,
    password: str,
    to_email: str,
    subject_prefix: str,
    attachments: list[Path],
    smtp_server: str = "",
    smtp_port: str = "",
    report_payload: dict | None = None,
) -> None:
    server_host, server_port, mode = resolve_smtp(from_email, smtp_server, smtp_port)
    recipients = [addr.strip() for addr in to_email.split(",") if addr.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO is empty")

    latest_date = attachments[0].name.split("-weekly-geography")[0]
    subject = f"{subject_prefix} {latest_date}".strip()
    run_url = build_run_url()

    report_payload = report_payload or {}
    body_lines = [
        "高中地理热点周报已生成，附件包含 Markdown 周报和 JSON 结构化数据。",
        "",
        "本期摘要：",
        *build_summary_lines(report_payload),
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if run_url:
        body_lines.extend(["", f"GitHub Actions 运行记录：{run_url}"])
    body_lines.extend(["", "请在正式备课或发布前打开权威引用链接核验具体事件事实。"])

    message = EmailMessage()
    message["From"] = formataddr(("TrendRadar", from_email))
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content("\n".join(body_lines), charset="utf-8")
    message.add_alternative(build_summary_html(report_payload), subtype="html")

    for attachment in attachments:
        attach_file(message, attachment)

    print(f"[geography-email] SMTP: {server_host}:{server_port} ({mode})")
    print(f"[geography-email] To: {', '.join(recipients)}")
    print(f"[geography-email] Attachments: {', '.join(path.name for path in attachments)}")

    if mode == "ssl":
        with smtplib.SMTP_SSL(server_host, server_port, timeout=30) as server:
            server.login(from_email, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(server_host, server_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(from_email, password)
            server.send_message(message)

    print("[geography-email] Email sent")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Email latest geography weekly report attachments.")
    parser.add_argument("--report-dir", default="output/geography", help="Directory containing weekly geography reports.")
    parser.add_argument("--subject-prefix", default="高中地理热点周报", help="Email subject prefix.")
    parser.add_argument("--require-config", action="store_true", help="Fail instead of skipping when EMAIL_* config is missing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from_email = os.environ.get("EMAIL_FROM", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()
    to_email = os.environ.get("EMAIL_TO", "").strip()

    missing = [name for name, value in {
        "EMAIL_FROM": from_email,
        "EMAIL_PASSWORD": password,
        "EMAIL_TO": to_email,
    }.items() if not value]

    if missing:
        message = f"[geography-email] Missing {', '.join(missing)}; skip email delivery"
        if args.require_config:
            raise SystemExit(message)
        print(message)
        return 0

    md_path, json_path = find_latest_report(Path(args.report_dir))
    attachments = [md_path]
    if json_path:
        attachments.append(json_path)
    report_payload = load_report_payload(json_path)

    send_email(
        from_email=from_email,
        password=password,
        to_email=to_email,
        subject_prefix=args.subject_prefix,
        attachments=attachments,
        smtp_server=os.environ.get("EMAIL_SMTP_SERVER", "").strip(),
        smtp_port=os.environ.get("EMAIL_SMTP_PORT", "").strip(),
        report_payload=report_payload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
