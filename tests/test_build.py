import json
import importlib.util
import tempfile
import unittest
from pathlib import Path


SITE_ROOT = Path(__file__).resolve().parents[1]


def find_workspace_root(site_root: Path) -> Path:
    """Locate the report archive for both the main checkout and git worktrees."""
    direct_root = site_root.parent
    if (direct_root / "archive").is_dir():
        return direct_root

    git_pointer = site_root / ".git"
    if git_pointer.is_file():
        git_dir = Path(git_pointer.read_text(encoding="utf-8").split(":", 1)[1].strip())
        common_site_root = git_dir.parents[2]
        worktree_root = common_site_root.parent
        if (worktree_root / "archive").is_dir():
            return worktree_root

    raise RuntimeError("Could not locate the beauty report workspace archive")


ROOT = find_workspace_root(SITE_ROOT)
BUILD_PATH = SITE_ROOT / "build.py"


def load_build_module():
    if not BUILD_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("beauty_intelligence_build", BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build_module()


class SiteBuildTests(unittest.TestCase):
    def valid_daily_report(self):
        return {
            "kind": "daily",
            "date": "2026-07-15",
            "title": "美妆竞对情报日报｜2026年7月15日",
            "source": "archive/日报/2026-07-15/beauty-daily-20260715.html",
        }

    def test_pages_workflow_checks_out_the_repository_before_uploading_public(self):
        workflow = (SITE_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("uses: actions/checkout@v4", workflow)

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

    def test_manifest_accepts_approved_variable_push_items(self):
        report = self.valid_daily_report()
        report["push"] = {
            "status": "approved",
            "heading": "昨日重点",
            "items": ["第一条。", "第二条。", "第三条。", "第四条。"],
            "detail_label": "查看完整日报",
        }
        self.assertEqual(build.validate_manifest({"reports": [report]}, ROOT), [report])

    def test_manifest_rejects_approved_push_without_items(self):
        report = self.valid_daily_report()
        report["push"] = {"status": "approved", "items": []}
        with self.assertRaisesRegex(ValueError, "push.items"):
            build.validate_manifest({"reports": [report]}, ROOT)

    def test_manifest_rejects_unknown_push_status(self):
        report = self.valid_daily_report()
        report["push"] = {"status": "ready", "items": ["第一条。"]}
        with self.assertRaisesRegex(ValueError, "push.status"):
            build.validate_manifest({"reports": [report]}, ROOT)

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

    def test_daily_template_uses_visible_tag_for_dimension_index(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        source = '''<html><head></head><body>
        <nav class="side" aria-label="日报条目"><a href="#item-1"><span>品牌名</span><b>#1</b></a></nav>
        <article class="card finance-card" id="item-1"><span class="tag">监管与原料</span></article>
        </body></html>'''
        rendered = build.decorate_report(source, "daily", "archive/example.html", {})
        self.assertIn("监管与原料", rendered)
        self.assertNotIn(">投融资</span><b>#1</b>", rendered)

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
        self.assertIn("2026-07-15", home)
        self.assertIn("beauty-daily-20260715", home)

    def test_github_pages_build_uses_repository_base_path_and_keeps_home_images(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        build.build_site(ROOT, self.output, base_path="/beauty-intel")
        home = (self.output / "index.html").read_text(encoding="utf-8")
        daily = (self.output / "daily/2026-07-14/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/beauty-intel/calendar/"', home)
        self.assertIn('href="/beauty-intel/pdf/beauty-daily-20260714.pdf"', daily)
        self.assertIn('href="/beauty-intel/assets/site-shell.css"', daily)
        self.assertTrue((self.output / "assets/01-nmpa-new-ingredient-rule.png").is_file())

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
        original_site_dir = build.SITE_DIR
        try:
            build.SITE_DIR = ROOT / "site"
            build.prepare_hosted_output(self.output, hosted)
        finally:
            build.SITE_DIR = original_site_dir
        self.assertTrue((hosted / "dist/server/index.js").is_file())
        self.assertTrue((hosted / "dist/assets/index.html").is_file())
        self.assertTrue((hosted / "static/index.html").is_file())

    def test_manifest_sources_exist(self):
        self.assertIsNotNone(build, "site/build.py must exist")
        data = json.loads((ROOT / "site/data/published.json").read_text(encoding="utf-8"))
        reports = build.validate_manifest(data, ROOT)
        self.assertEqual(len(reports), 6)


if __name__ == "__main__":
    unittest.main()
