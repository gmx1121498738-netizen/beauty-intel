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


def select_reports(reports: list[dict], target_dates: list[str]) -> list[dict]:
    selected = []
    for target_date in target_dates:
        report = select_report(reports, target_date)
        if report is None:
            raise ValueError(f"No approved daily push for {target_date}")
        selected.append(report)
    return selected


def select_weekly_report(reports: list[dict], target_week: str) -> dict | None:
    matches = [
        report
        for report in reports
        if report.get("kind") == "weekly" and report.get("week") == target_week
    ]
    if len(matches) > 1:
        raise ValueError(f"Duplicate weekly reports for {target_week}")
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


def weekly_report_url(base_url: str, week: str) -> str:
    return f"{base_url.rstrip('/')}/weekly/{week}/"


def build_card(report: dict, base_url: str) -> dict:
    report_date = datetime.strptime(report["date"], "%Y-%m-%d")
    push = report["push"]
    heading = push.get("heading", "昨日重点")
    summary = "\n".join(
        f"{index}. {item.strip()}"
        for index, item in enumerate(push["items"], start=1)
    )
    summary += f"\n\n*数据日期：{report_date.month}月{report_date.day}日*"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": push.get("card_title", "美妆情报Bot｜行业日报"),
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


def build_multi_day_card(reports: list[dict], base_url: str) -> dict:
    """Build one manually-triggered card for a contiguous set of approved dailies."""
    if not reports:
        raise ValueError("reports is required")

    dates = [datetime.strptime(report["date"], "%Y-%m-%d") for report in reports]
    if dates[0].month == dates[-1].month:
        title = f"美妆情报Bot｜{dates[0].month}月{dates[0].day}—{dates[-1].day}日日报"
    else:
        title = (
            f"美妆情报Bot｜{dates[0].month}月{dates[0].day}日—"
            f"{dates[-1].month}月{dates[-1].day}日日报"
        )
    elements = []
    for report, report_date in zip(reports, dates):
        items = report.get("push", {}).get("items", [])
        lines = "\n".join(f"{index}. {item.strip()}" for index, item in enumerate(items, 1))
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{report_date.month}月{report_date.day}日**\n{lines}",
                },
            }
        )
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {
                            "tag": "plain_text",
                            "content": f"查看{report_date.month}月{report_date.day}日日报",
                        },
                        "url": report_url(base_url, report["date"]),
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def build_weekly_card(report: dict, base_url: str) -> dict:
    push = report["push"]
    year, week_number = report["week"].split("-W", 1)
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
                "content": f"美妆情报Bot｜{year}年第{int(week_number)}周周报",
            },
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{push.get('heading', '本周重点')}**\n\n{summary}",
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
                            "content": push.get("detail_label", "点开查看完整周报"),
                        },
                        "url": weekly_report_url(base_url, report["week"]),
                    }
                ],
            },
        ],
    }


def build_stage_update_card(weekly: dict, dailies: list[dict], base_url: str) -> dict:
    """Build one card that keeps the weekly and each daily update distinct."""
    year, week_number = weekly["week"].split("-W", 1)
    weekly_items = weekly["push"]["items"]
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**周报｜%s年第%s周**\n%s"
                % (
                    year,
                    int(week_number),
                    "\n".join(f"{index}. {item.strip()}" for index, item in enumerate(weekly_items, 1)),
                ),
            },
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "type": "primary",
                    "text": {"tag": "plain_text", "content": "查看完整周报"},
                    "url": weekly_report_url(base_url, weekly["week"]),
                }
            ],
        },
    ]
    for report in dailies:
        report_date = datetime.strptime(report["date"], "%Y-%m-%d")
        items = report.get("push", {}).get("stage_items", report.get("push", {}).get("items", []))
        if not items:
            raise ValueError(f"No stage-update items for {report['date']}")
        lines = "\n".join(f"{index}. {item.strip()}" for index, item in enumerate(items, 1))
        elements.extend([
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{report_date.month}月{report_date.day}日日报**\n{lines}",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": f"查看{report_date.month}月{report_date.day}日日报"},
                        "url": report_url(base_url, report["date"]),
                    }
                ],
            },
        ])
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "美妆情报Bot｜阶段更新"}},
        "elements": elements,
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
    parser.add_argument("--dates", help="Comma-separated dates for one manual summary card")
    parser.add_argument("--week", help="Target weekly report in YYYY-Www format")
    parser.add_argument("--stage-week", help="Weekly report for one combined stage-update card")
    parser.add_argument("--stage-dates", help="Comma-separated daily dates for one combined stage-update card")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout

    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        stage_selected = bool(args.stage_week or args.stage_dates)
        selections = sum(bool(value) for value in (args.date, args.dates, args.week, stage_selected))
        if selections != 1:
            raise ValueError("Specify exactly one report target or one stage update")
        if stage_selected:
            if not args.stage_week or not args.stage_dates:
                raise ValueError("Stage update requires both --stage-week and --stage-dates")
            weekly = select_weekly_report(data.get("reports", []), args.stage_week)
            if weekly is None:
                raise ValueError(f"No approved weekly push for {args.stage_week}")
            stage_dates = [date.strip() for date in args.stage_dates.split(",") if date.strip()]
            if not stage_dates:
                raise ValueError("Stage update requires at least one daily date")
            dailies = select_reports(data.get("reports", []), stage_dates)
        elif args.week:
            report = select_weekly_report(data.get("reports", []), args.week)
            if report is None:
                raise ValueError(f"No approved weekly push for {args.week}")
        elif args.dates:
            target_dates = [date.strip() for date in args.dates.split(",") if date.strip()]
            reports = select_reports(data.get("reports", []), target_dates)
        else:
            target_date = args.date
            report = select_report(data.get("reports", []), target_date)
            if report is None:
                raise ValueError(f"No approved daily push for {target_date}")

        base_url = environ.get("SITE_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("SITE_BASE_URL is required")
        if stage_selected:
            card = build_stage_update_card(weekly, dailies, base_url)
        elif args.week:
            card = build_weekly_card(report, base_url)
        elif args.dates:
            card = build_multi_day_card(reports, base_url)
        else:
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
        if stage_selected:
            print(
                f"SENT: combined stage update for {args.stage_week} and {','.join(stage_dates)}",
                file=stdout,
            )
        elif args.week:
            print(f"SENT: approved weekly push for {args.week}", file=stdout)
        elif args.dates:
            print(f"SENT: approved multi-day push for {','.join(target_dates)}", file=stdout)
        else:
            print(f"SENT: approved daily push for {target_date}", file=stdout)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
