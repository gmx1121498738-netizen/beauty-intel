import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SITE_ROOT / "push_daily.py"


def load_module():
    if not MODULE_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("push_daily", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


push_daily = load_module()


def make_report(date="2026-07-15", status="approved", items=None):
    return {
        "kind": "daily",
        "date": date,
        "title": f"美妆竞对情报日报｜{date}",
        "push": {
            "status": status,
            "heading": "昨日重点",
            "items": items if items is not None else ["重点一"],
            "detail_label": "查看完整日报",
        },
    }


class ReportSelectionTests(unittest.TestCase):
    def test_select_reports_returns_each_approved_requested_date_in_order(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        reports = [
            make_report("2026-07-17", items=["17日重点"]),
            make_report("2026-07-18", items=["18日重点"]),
            make_report("2026-07-19", items=["19日重点"]),
        ]
        selected = push_daily.select_reports(reports, ["2026-07-17", "2026-07-18", "2026-07-19"])
        self.assertEqual([report["date"] for report in selected], ["2026-07-17", "2026-07-18", "2026-07-19"])

    def test_select_report_returns_only_approved_target_date(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        report = make_report()
        self.assertEqual(push_daily.select_report([report], "2026-07-15"), report)

    def test_select_report_stays_silent_for_missing_or_draft_report(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        draft = make_report(status="draft")
        self.assertIsNone(push_daily.select_report([draft], "2026-07-15"))
        self.assertIsNone(push_daily.select_report([], "2026-07-15"))

    def test_select_report_rejects_duplicate_target_date(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            push_daily.select_report([make_report(), make_report()], "2026-07-15")

    def test_select_report_rejects_approved_empty_summary(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        with self.assertRaisesRegex(ValueError, "push.items"):
            push_daily.select_report(
                [make_report(status="approved", items=[])],
                "2026-07-15",
            )

    def test_shanghai_yesterday_uses_shanghai_calendar_date(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        now = datetime(2026, 7, 16, 0, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(push_daily.shanghai_yesterday(now), "2026-07-15")


class FeishuCardTests(unittest.TestCase):
    def test_multi_day_card_separates_each_report_and_links_to_each_daily_page(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        reports = [
            make_report("2026-07-17", items=["17日重点"]),
            make_report("2026-07-18", items=["18日重点"]),
            make_report("2026-07-19", items=["19日重点"]),
        ]
        card = push_daily.build_multi_day_card(
            reports,
            "https://gmx1121498738-netizen.github.io/beauty-intel",
        )

        self.assertEqual(card["header"]["title"]["content"], "美妆情报Bot｜7月17—19日日报")
        content = card["elements"][0]["text"]["content"]
        self.assertIn("**7月17日**", content)
        self.assertIn("**7月18日**", content)
        self.assertIn("**7月19日**", content)
        self.assertIn("17日重点", content)
        self.assertIn("19日重点", content)
        self.assertIn("/daily/2026-07-17/", content)
        self.assertIn("/daily/2026-07-19/", content)
    def test_card_uses_bot_name_all_reviewed_items_and_daily_url(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        report = make_report(items=["重点一", "重点二", "重点三", "重点四"])
        card = push_daily.build_card(
            report,
            "https://gmx1121498738-netizen.github.io/beauty-intel/",
        )

        self.assertEqual(
            card["header"]["title"]["content"],
            "美妆情报Bot｜7月15日日报",
        )
        content = card["elements"][0]["text"]["content"]
        for index, item in enumerate(report["push"]["items"], start=1):
            self.assertIn(f"{index}. {item}", content)
        self.assertEqual(
            card["elements"][1]["actions"][0]["url"],
            "https://gmx1121498738-netizen.github.io/beauty-intel/daily/2026-07-15/",
        )

    def test_card_uses_reviewed_heading_and_button_label(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        report = make_report(items=["唯一重点"])
        report["push"]["heading"] = "昨日核心情报"
        report["push"]["detail_label"] = "打开日报网页"
        card = push_daily.build_card(report, "https://example.com/beauty")

        self.assertIn("**昨日核心情报**", card["elements"][0]["text"]["content"])
        self.assertEqual(
            card["elements"][1]["actions"][0]["text"]["content"],
            "打开日报网页",
        )


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class FeishuWebhookTests(unittest.TestCase):
    def test_signature_matches_feishu_hmac_algorithm(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        self.assertEqual(
            push_daily.feishu_signature("1599360473", "test"),
            "NVcdmaRhTlOqmXksontxmKEP4AYWAMD5VOczwSqarks=",
        )

    def test_send_webhook_posts_signed_interactive_card(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"code": 0, "msg": "success"})

        card = {"header": {"title": {"content": "美妆情报Bot"}}}
        result = push_daily.send_webhook(
            "https://open.feishu.cn/open-apis/bot/v2/hook/example",
            card,
            secret="test",
            timestamp="1599360473",
            opener=opener,
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["payload"]["msg_type"], "interactive")
        self.assertEqual(captured["payload"]["card"], card)
        self.assertEqual(captured["payload"]["timestamp"], "1599360473")
        self.assertEqual(
            captured["payload"]["sign"],
            "NVcdmaRhTlOqmXksontxmKEP4AYWAMD5VOczwSqarks=",
        )

    def test_send_webhook_raises_sanitized_error_for_feishu_rejection(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/private-token"
        secret = "private-secret"

        def opener(request, timeout):
            return FakeResponse({"code": 19021, "msg": "sign match fail"})

        with self.assertRaisesRegex(RuntimeError, "19021") as context:
            push_daily.send_webhook(
                webhook,
                {},
                secret=secret,
                timestamp="1599360473",
                opener=opener,
            )

        self.assertNotIn(webhook, str(context.exception))
        self.assertNotIn(secret, str(context.exception))

    def test_send_webhook_hides_credentials_on_transport_failure(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/private-token"
        secret = "private-secret"

        def opener(request, timeout):
            raise OSError(f"network failed for {webhook} using {secret}")

        with self.assertRaisesRegex(RuntimeError, "request failed") as context:
            push_daily.send_webhook(webhook, {}, secret=secret, opener=opener)

        self.assertNotIn(webhook, str(context.exception))
        self.assertNotIn(secret, str(context.exception))


class PushDailyCliTests(unittest.TestCase):
    def write_manifest(self, reports):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "published.json"
        path.write_text(json.dumps({"reports": reports}, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(temp_dir.cleanup)
        return path

    def test_missing_report_is_a_silent_success(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        output = io.StringIO()
        result = push_daily.main(
            ["--manifest", str(self.write_manifest([])), "--date", "2026-07-15"],
            environ={},
            stdout=output,
        )
        self.assertEqual(result, 0)
        self.assertIn("SKIP", output.getvalue())

    def test_dry_run_prints_card_without_webhook(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        output = io.StringIO()
        result = push_daily.main(
            [
                "--manifest",
                str(self.write_manifest([make_report(items=["重点一", "重点二"])])),
                "--date",
                "2026-07-15",
                "--dry-run",
            ],
            environ={"SITE_BASE_URL": "https://example.com/beauty"},
            stdout=output,
        )
        self.assertEqual(result, 0)
        self.assertIn("美妆情报Bot", output.getvalue())
        self.assertIn("https://example.com/beauty/daily/2026-07-15/", output.getvalue())

    def test_real_send_requires_webhook_url(self):
        self.assertIsNotNone(push_daily, "push_daily.py must exist")
        output = io.StringIO()
        result = push_daily.main(
            [
                "--manifest",
                str(self.write_manifest([make_report()])),
                "--date",
                "2026-07-15",
            ],
            environ={"SITE_BASE_URL": "https://example.com/beauty"},
            stdout=output,
        )
        self.assertEqual(result, 2)
        self.assertIn("FEISHU_WEBHOOK_URL", output.getvalue())


class PushWorkflowTests(unittest.TestCase):
    def test_workflow_supports_a_manual_multi_day_summary(self):
        workflow = (SITE_ROOT / ".github" / "workflows" / "push-feishu-daily.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("target_dates", workflow)
        self.assertIn("--dates", workflow)

    def test_workflow_runs_at_eleven_with_secrets_and_concurrency(self):
        workflow_path = SITE_ROOT / ".github/workflows/push-feishu-daily.yml"
        self.assertTrue(workflow_path.is_file(), "push workflow must exist")
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn('cron: "0 3 * * *"', workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("SITE_BASE_URL", workflow)
        self.assertIn("FEISHU_WEBHOOK_URL", workflow)
        self.assertIn("FEISHU_WEBHOOK_SECRET", workflow)
        self.assertIn("python3 push_daily.py", workflow)
        self.assertIn("dry_run", workflow)


if __name__ == "__main__":
    unittest.main()
