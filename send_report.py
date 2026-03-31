#!/usr/bin/env python3
"""
USD/JPY Report Email Sender
============================
Sends daily, weekly, or SMC reports with .md and .pdf attachments via SMTP.

Usage:
    python3 send_report.py <report.md> [--type daily|weekly|smc] [extra_files ...]

Auto-detects report type from the file path if --type is not specified.
Automatically finds the matching .pdf alongside the .md file.

Configuration:
    Reads SMTP settings from config.yaml
    Email password from environment variable: USDJPY_EMAIL_PASSWORD
"""

import argparse
import os
import re
import sys
import smtplib
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def detect_report_type(md_path):
    """Auto-detect report type from file path."""
    name = os.path.basename(md_path)
    if name.startswith("smc_"):
        return "smc"
    if "/weekly/" in md_path:
        return "weekly"
    return "daily"


def extract_date(md_path):
    """Extract YYYY-MM-DD from filename."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(md_path))
    return m.group(1) if m else ""


def extract_summary(md_text, report_type):
    """Extract a one-line email body summary from the report markdown."""
    if report_type == "smc":
        # Hero verdict: direction + grade + entry
        direction = "NEUTRAL"
        grade = "?"
        entry = ""
        m = re.search(r"\*\*Direction:\*\*\s*(\w+)", md_text)
        if m:
            direction = m.group(1)
        m = re.search(r"\*\*Confluence Score:\*\*\s*([\d.]+)\s*.*?Grade\s*\*\*(\w\+?)\*\*", md_text)
        if m:
            grade = m.group(2)
        m = re.search(r"\|\s*Entry\s*\|\s*([\d.]+)", md_text)
        if m:
            entry = m.group(1)
        return f"{direction} | Grade {grade} | Entry {entry}" if entry else f"{direction} | Grade {grade} | No entry"

    # Daily/Weekly: Module 07 summary
    m = re.search(r"\*\*Bias:\s*(.+?)\*\*", md_text)
    bias = m.group(1).strip() if m else "N/A"
    m = re.search(r"\*\*Score:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    score = m.group(1).strip() if m else ""
    return f"Bias: {bias} | {score}" if score else f"Bias: {bias}"


def extract_smc_grade(md_text):
    """Extract grade for SMC subject line."""
    m = re.search(r"Grade\s*\*\*(\w\+?)\*\*", md_text)
    return m.group(1) if m else ""


def build_subject(report_type, report_date, md_text):
    """Build email subject line based on report type."""
    if report_type == "smc":
        grade = extract_smc_grade(md_text)
        suffix = f" [{grade}]" if grade else ""
        return f"SMC Pulse — SMC Report {report_date}{suffix}"
    if report_type == "weekly":
        return f"SMC Pulse — Weekly Report {report_date}"
    return f"SMC Pulse — Daily Report {report_date}"


def send_report(report_path, report_type=None, extra_files=None):
    config = load_config()
    email_config = config.get("email", {})

    if not email_config.get("enabled", False):
        print("Email is disabled in config.yaml. Skipping.")
        return False

    # Get credentials
    smtp_host = email_config["smtp_host"]
    smtp_port = email_config["smtp_port"]
    from_addr = email_config["from_address"]
    to_addr = email_config["to_address"]
    password = os.environ.get("USDJPY_EMAIL_PASSWORD")

    if not password:
        print("ERROR: USDJPY_EMAIL_PASSWORD environment variable not set.")
        return False

    if to_addr == "YOUR_PERSONAL_EMAIL":
        print("ERROR: Update 'to_address' in config.yaml with your actual email.")
        return False

    report_path = Path(report_path)
    if not report_path.exists() or report_path.stat().st_size == 0:
        print(f"ERROR: Report missing or empty: {report_path}")
        return False

    # Auto-detect type if not provided
    if not report_type:
        report_type = detect_report_type(str(report_path))

    # Read report
    report_text = report_path.read_text(encoding="utf-8")
    report_date = extract_date(str(report_path))

    # Build email
    msg = MIMEMultipart("mixed")
    msg["From"] = f"SMC Pulse <{from_addr}>"
    msg["To"] = to_addr
    msg["Subject"] = build_subject(report_type, report_date, report_text)

    # Body: one-line summary
    summary = extract_summary(report_text, report_type)
    msg.attach(MIMEText(summary, "plain", "utf-8"))

    attachment_count = 0

    # Attach the .md file
    md_att = MIMEText(report_text, "plain", "utf-8")
    md_att.add_header("Content-Disposition", "attachment", filename=report_path.name)
    msg.attach(md_att)
    attachment_count += 1
    print(f"  Attached: {report_path.name}")

    # Auto-find matching .pdf
    pdf_path = report_path.with_suffix(".pdf")
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        with open(pdf_path, "rb") as f:
            pdf_part = MIMEBase("application", "pdf")
            pdf_part.set_payload(f.read())
            encoders.encode_base64(pdf_part)
            pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
            msg.attach(pdf_part)
        attachment_count += 1
        print(f"  Attached: {pdf_path.name}")

    # Attach any extra files (PNGs, etc.)
    for fpath in (extra_files or []):
        fp = Path(fpath)
        if not fp.exists():
            continue
        if fp.suffix.lower() == ".png":
            with open(fp, "rb") as f:
                img = MIMEImage(f.read(), name=fp.name)
                img.add_header("Content-Disposition", "attachment", filename=fp.name)
                msg.attach(img)
            attachment_count += 1
            print(f"  Attached: {fp.name}")
        elif fp.suffix.lower() == ".pdf":
            with open(fp, "rb") as f:
                pdf_part = MIMEBase("application", "pdf")
                pdf_part.set_payload(f.read())
                encoders.encode_base64(pdf_part)
                pdf_part.add_header("Content-Disposition", "attachment", filename=fp.name)
                msg.attach(pdf_part)
            attachment_count += 1
            print(f"  Attached: {fp.name}")

    # Send
    try:
        if smtp_port == 587:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(from_addr, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(from_addr, password)
                server.send_message(msg)
        print(f"  Sent to {to_addr} ({attachment_count} attachments)")
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR: SMTP authentication failed. Check email password / app password.")
        return False
    except smtplib.SMTPException as e:
        print(f"ERROR: SMTP error: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send USD/JPY report via email.")
    parser.add_argument("report", help="Path to .md report file")
    parser.add_argument("--type", choices=["daily", "weekly", "smc"], default=None,
                        help="Report type (auto-detected if omitted)")
    parser.add_argument("extra", nargs="*", help="Extra files to attach (PNGs, etc.)")
    args = parser.parse_args()

    if not Path(args.report).exists():
        print(f"ERROR: Report not found: {args.report}")
        sys.exit(1)

    ok = send_report(args.report, args.type, args.extra if args.extra else None)
    sys.exit(0 if ok else 1)
