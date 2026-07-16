#!/usr/bin/env python3
"""Send an approved beauty-daily summary to a fixed Feishu group bot."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def shanghai_yesterday(now: datetime | None = None) -> str:
    current = now.astimezone(SHANGHAI) if now else datetime.now(SHANGHAI)
    return (current.date() - timedelta(days=1)).isoformat()


def select_report(reports: list[dict], target_date: str) -> dict | None:
    matches = [
        report
        for report in reports
        if report.get("kind") == "daily" and report.get("date") == target_date
    ]
    if len(matches) > 1:
        raise ValueError(f"Duplicate daily reports for {target_date}")
    if not matches:
        return None
    report = matches[0]
    if report.get("push", {}).get("status") != "approved":
        return None
    items = report["push"].get("items")
    if (
        not isinstance(items, list)
        or not items
        or any(not isinstance(item, str) or not item.strip() for item in items)
    ):
        raise ValueError("approved push.items must contain non-empty strings")
    return report


def report_url(base_url: str, report_date: str) -> str:
    return f"{base_url.rstrip('/')}/daily/{report_date}/"


def build_card(report: dict, base_url: str) -> dict:
    report_date = datetime.strptime(report["date"], "%Y-%m-%d")
    push = report["push"]
    heading = push.get("heading", "昨日重点")
    summary = "\n".join(
        f"{index}. {item.strip()}"
        for index, item in enumerate(push["items"], start=1)
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"美妆情报Bot｜{report_date.month}月{report_date.day}日日报",
            },
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{heading}**\n\n{summary}",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {
                            "tag": "plain_text",
                            "content": push.get("detail_label", "查看完整日报"),
                        },
                        "url": report_url(base_url, report["date"]),
                    }
                ],
            },
        ],
    }


def feishu_signature(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_webhook(
    webhook_url: str,
    card: dict,
    secret: str = "",
    timestamp: str | None = None,
    opener=urlopen,
) -> dict:
    payload = {"msg_type": "interactive", "card": card}
    if secret:
        timestamp = timestamp or str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = feishu_signature(timestamp, secret)

    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Feishu webhook request failed") from error

    code = result.get("code", result.get("StatusCode"))
    if code != 0:
        message = result.get("msg", result.get("StatusMessage", "unknown error"))
        raise RuntimeError(f"Feishu webhook rejected request ({code}): {message}")
    return result


def main(argv=None, environ=None, stdout=None, send_fn=send_webhook) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/published.json")
    parser.add_argument("--date", help="Target report date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout

    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        target_date = args.date or shanghai_yesterday()
        report = select_report(data.get("reports", []), target_date)
        if report is None:
            print(f"SKIP: no approved daily push for {target_date}", file=stdout)
            return 0

        base_url = environ.get("SITE_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("SITE_BASE_URL is required")
        card = build_card(report, base_url)
        if args.dry_run:
            print(
                json.dumps(
                    {"msg_type": "interactive", "card": card},
                    ensure_ascii=False,
                    indent=2,
                ),
                file=stdout,
            )
            return 0

        webhook_url = environ.get("FEISHU_WEBHOOK_URL", "").strip()
        if not webhook_url:
            raise ValueError("FEISHU_WEBHOOK_URL is required for delivery")
        send_fn(
            webhook_url,
            card,
            secret=environ.get("FEISHU_WEBHOOK_SECRET", "").strip(),
        )
        print(f"SENT: approved daily push for {target_date}", file=stdout)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
