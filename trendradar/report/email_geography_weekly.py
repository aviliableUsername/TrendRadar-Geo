# coding=utf-8
"""
Email the latest high school geography weekly report as file attachments.

The script is intentionally standard-library only so it can run in GitHub
Actions after report generation without adding dependencies.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
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


def send_email(
    from_email: str,
    password: str,
    to_email: str,
    subject_prefix: str,
    attachments: list[Path],
    smtp_server: str = "",
    smtp_port: str = "",
) -> None:
    server_host, server_port, mode = resolve_smtp(from_email, smtp_server, smtp_port)
    recipients = [addr.strip() for addr in to_email.split(",") if addr.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO is empty")

    latest_date = attachments[0].name.split("-weekly-geography")[0]
    subject = f"{subject_prefix} {latest_date}".strip()
    run_url = build_run_url()

    body_lines = [
        "高中地理热点周报已生成，附件包含 Markdown 周报和 JSON 结构化数据。",
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

    send_email(
        from_email=from_email,
        password=password,
        to_email=to_email,
        subject_prefix=args.subject_prefix,
        attachments=attachments,
        smtp_server=os.environ.get("EMAIL_SMTP_SERVER", "").strip(),
        smtp_port=os.environ.get("EMAIL_SMTP_PORT", "").strip(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
