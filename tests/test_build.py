import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_PATH = ROOT / "site/build.py"


def load_build_module():
    if not BUILD_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("beauty_intelligence_build", BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build_module()


class SiteBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "public"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manifest_rejects_unapproved_markdown_source(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        data = {
            "reports": [
                {
                    "kind": "daily",
                    "date": "2026-07-15",
                    "source": "archive/日报/2026-07-15/7月15日-正式初稿.md",
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "HTML"):
            build.validate_manifest(data, ROOT)

    def test_daily_route_is_date_based(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        self.assertEqual(
            build.route_for({"kind": "daily", "date": "2026-07-14"}),
            "daily/2026-07-14/index.html",
        )

    def test_weekly_route_is_week_based(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        self.assertEqual(
            build.route_for({"kind": "weekly", "week": "2026-W29"}),
            "weekly/2026-W29/index.html",
        )

    def test_daily_template_uses_dimension_index_and_clickable_volume_dates(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        source = '''<html><head></head><body>
        <nav class="side" aria-label="日报条目"><a href="#item-1"><span>品牌名</span><b>#1</b></a></nav>
        <article class="card brand-card" id="item-1"></article>
        <div class="date-strip"><div class="date-cell">7/10<b>6</b></div><div class="date-cell active">7/11<b>2</b></div></div>
        </body></html>'''
        routes = {"2026-07-10": "/daily/2026-07-10/"}
        rendered = build.decorate_report(source, "daily", "archive/example.html", routes)
        self.assertIn("品牌动态", rendered)
        self.assertIn('href="/daily/2026-07-10/"', rendered)
        self.assertIn('href="/calendar/?date=2026-07-11"', rendered)

    def test_calendar_contains_date_targets_for_volume_fallback(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        rendered = build.calendar_cells(
            [{"kind": "daily", "date": "2026-07-10", "title": "日报"}]
        )
        self.assertIn('data-date="2026-07-11"', rendered)

    def test_build_creates_navigation_and_archive_pages(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output)
        self.assertTrue((self.output / "calendar/index.html").is_file())
        self.assertTrue((self.output / "weekly/index.html").is_file())
        self.assertTrue((self.output / "search/index.html").is_file())
        daily = (self.output / "daily/2026-07-14/index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("日报｜日历｜周报｜搜索", daily)

    def test_homepage_uses_latest_published_daily(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output)
        home = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("2026-07-14", home)
        self.assertIn("beauty-daily-20260714", home)

    def test_published_daily_copies_the_confirmed_pdf_and_shows_export_link(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output)
        daily = (self.output / "daily/2026-07-14/index.html").read_text(encoding="utf-8")
        self.assertIn("导出 PDF", daily)
        self.assertIn("/pdf/beauty-daily-20260714.pdf", daily)
        self.assertTrue((self.output / "pdf/beauty-daily-20260714.pdf").is_file())

    def test_search_page_contains_only_published_reports(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output)
        page = (self.output / "search/index.html").read_text(encoding="utf-8")
        self.assertIn("2026-W29", page)
        self.assertNotIn("7月15日-正式初稿", page)

    def test_prepare_hosted_output_contains_worker_and_static_site(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output)
        hosted = Path(self.temp_dir.name) / "hosted"
        build.prepare_hosted_output(self.output, hosted)
        self.assertTrue((hosted / "dist/server/index.js").is_file())
        self.assertTrue((hosted / "dist/assets/index.html").is_file())
        self.assertTrue((hosted / "static/index.html").is_file())

    def test_manifest_sources_exist(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        data = json.loads((ROOT / "site/data/published.json").read_text(encoding="utf-8"))
        reports = build.validate_manifest(data, ROOT)
        self.assertEqual(len(reports), 5)


if __name__ == "__main__":
    unittest.main()
