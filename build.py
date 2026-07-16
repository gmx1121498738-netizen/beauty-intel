#!/usr/bin/env python3
"""Build the Beauty Intelligence static site from approved report templates."""

from __future__ import annotations

import calendar
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path
from string import Template


SITE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = SITE_DIR / "assets"
TEMPLATES_DIR = SITE_DIR / "templates"


def route_for(report: dict) -> str:
    """Return the public route for a report entry."""
    if report.get("kind") == "daily":
        return f"daily/{report['date']}/index.html"
    if report.get("kind") == "weekly":
        return f"weekly/{report['week']}/index.html"
    raise ValueError("Report kind must be daily or weekly")


def site_url(path: str, base_path: str = "") -> str:
    """Build a root-relative link that also works from a GitHub Pages project URL."""
    normal_path = "/" + path.lstrip("/")
    normal_base = "/" + base_path.strip("/") if base_path.strip("/") else ""
    return normal_base + normal_path


def validate_manifest(data: dict, root: Path) -> list[dict]:
    """Validate only explicitly published, standalone HTML reports."""
    reports = data.get("reports")
    if not isinstance(reports, list) or not reports:
        raise ValueError("published.json must contain at least one report")

    seen_routes: set[str] = set()
    for report in reports:
        kind = report.get("kind")
        if kind not in {"daily", "weekly"}:
            raise ValueError("Report kind must be daily or weekly")
        if kind == "daily":
            date.fromisoformat(report.get("date", ""))
        else:
            if not re.fullmatch(r"\d{4}-W\d{2}", report.get("week", "")):
                raise ValueError("Weekly reports need a YYYY-Www week key")

        source = report.get("source", "")
        if Path(source).suffix.lower() != ".html":
            raise ValueError("Only approved HTML reports can be published")
        if not (root / source).is_file():
            raise ValueError(f"Published source is missing: {source}")
        pdf = report.get("pdf")
        if pdf and (Path(pdf).suffix.lower() != ".pdf" or not (root / pdf).is_file()):
            raise ValueError(f"Published PDF is missing or invalid: {pdf}")
        route = route_for(report)
        if route in seen_routes:
            raise ValueError(f"Duplicate public route: {route}")
        seen_routes.add(route)
    return reports


def load_manifest(root: Path) -> list[dict]:
    data = json.loads((root / "site/data/published.json").read_text(encoding="utf-8"))
    return validate_manifest(data, root)


def nav_html(active: str, pdf_href: str = "", base_path: str = "") -> str:
    labels = (("daily", "日报", "/"), ("calendar", "日历", "/calendar/"), ("weekly", "周报", "/weekly/"), ("search", "搜索", "/search/"))
    links = []
    for key, label, href in labels:
        current = ' aria-current="page"' if active == key else ""
        links.append(f'<a href="{site_url(href, base_path)}"{current}>{label}</a>')
    export = f'<a class="site-pdf-export" href="{pdf_href}" download>导出 PDF</a>' if pdf_href else ""
    return '<nav class="site-global-nav" aria-label="日报｜日历｜周报｜搜索">' + "<span>｜</span>".join(links) + export + "</nav>"


DIMENSION_LABELS = {
    "brand-card": "品牌动态",
    "market-card": "市场版图",
    "channel-card": "渠道生态",
    "finance-card": "投融资",
    "other-card": "其他动态",
}


def replace_dimension_index(source_html: str) -> str:
    """Change the source template's article index from brand names to dimensions."""
    dimensions: dict[str, str] = {}
    for article in re.finditer(r"<article\b([^>]*)>", source_html, flags=re.I):
        attrs = article.group(1)
        item_id = re.search(r'\bid="([^"]+)"', attrs, flags=re.I)
        classes = re.search(r'\bclass="([^"]+)"', attrs, flags=re.I)
        if not item_id or not classes:
            continue
        label = next(
            (DIMENSION_LABELS[class_name] for class_name in classes.group(1).split() if class_name in DIMENSION_LABELS),
            "行业动态",
        )
        dimensions[item_id.group(1)] = label

    def replace_nav(nav_match: re.Match) -> str:
        nav = nav_match.group(0).replace('aria-label="日报条目"', 'aria-label="日报维度索引"')

        def replace_link(link_match: re.Match) -> str:
            link = link_match.group(0)
            target = re.search(r'href="#([^"]+)"', link)
            if not target or target.group(1) not in dimensions:
                return link
            return re.sub(r"(<span>).*?(</span>)", r"\1" + dimensions[target.group(1)] + r"\2", link, count=1, flags=re.S)

        return re.sub(r"<a\b[^>]*href=\"#[^\"]+\"[^>]*>.*?</a>", replace_link, nav, flags=re.S | re.I)

    return re.sub(r"<nav\b[^>]*\bclass=\"side\"[^>]*>.*?</nav>", replace_nav, source_html, count=1, flags=re.S | re.I)


def link_volume_dates(source_html: str, daily_routes: dict[str, str], report_date: str = "", base_path: str = "") -> str:
    """Link every near-five-day volume card to its report or the calendar fallback."""
    year = report_date[:4] if report_date else next(iter(sorted(daily_routes)), "2026")[:4]

    def replace_cell(cell_match: re.Match) -> str:
        attrs, content = cell_match.group(1), cell_match.group(2)
        short_date = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", content)
        if not short_date:
            return cell_match.group(0)
        target_date = f"{year}-{int(short_date.group(1)):02d}-{int(short_date.group(2)):02d}"
        href = daily_routes.get(target_date, site_url(f"calendar/?date={target_date}", base_path))
        linked_attrs = re.sub(r'(\bclass=")([^"]*)"', r'\1\2 date-link"', attrs, count=1)
        return f'<a {linked_attrs} href="{href}">{content}</a>'

    return re.sub(
        r'<div\s+([^>]*\bclass="[^"]*date-cell[^"]*"[^>]*)>(.*?)</div>',
        replace_cell,
        source_html,
        flags=re.S | re.I,
    )


def decorate_report(
    source_html: str,
    active: str,
    source_path: str = "",
    daily_routes: dict[str, str] | None = None,
    report_date: str = "",
    pdf_href: str = "",
    base_path: str = "",
) -> str:
    """Add site navigation without changing the source report card markup."""
    if active == "daily":
        source_html = replace_dimension_index(source_html)
        source_html = link_volume_dates(source_html, daily_routes or {}, report_date, base_path)
    shell_link = f'<link rel="stylesheet" href="{site_url("assets/site-shell.css", base_path)}" />'
    if "site-shell.css" not in source_html:
        source_html = re.sub(r"</head>", shell_link + "\n</head>", source_html, count=1, flags=re.I)
    source_html = re.sub(
        r"<body\b[^>]*>",
        lambda match: match.group(0)[:-1] + f' data-site-section="{active}">',
        source_html,
        count=1,
        flags=re.I,
    )
    source_note = f"\n<!-- Published source: {html.escape(source_path)} -->" if source_path else ""
    return re.sub(r"(<body\b[^>]*>)", r"\1\n" + nav_html(active, pdf_href, base_path) + source_note, source_html, count=1, flags=re.I)


def render_template(name: str, **values: str) -> str:
    template = Template((TEMPLATES_DIR / name).read_text(encoding="utf-8"))
    return template.safe_substitute(values)


def archive_shell(title: str, active: str, body: str, script: str = "", base_path: str = "") -> str:
    return render_template(
        "archive.html",
        title=html.escape(title),
        nav=nav_html(active, base_path=base_path),
        shell_href=site_url("assets/site-shell.css", base_path),
        body=body,
        script=script,
    )


def calendar_cells(dailies: list[dict], base_path: str = "") -> str:
    by_date = {item["date"]: item for item in dailies}
    months = sorted({(date.fromisoformat(item["date"]).year, date.fromisoformat(item["date"]).month) for item in dailies})
    result: list[str] = []
    for year, month in months:
        month_name = f"{year} 年 {month} 月"
        rows = ['<section class="month-card"><h2>' + month_name + "</h2>", '<div class="weekday-row"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>', '<div class="calendar-grid">']
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            for day in week:
                iso = day.isoformat()
                if day.month != month:
                    rows.append('<span class="calendar-blank" aria-hidden="true"></span>')
                elif iso in by_date:
                    rows.append(f'<a class="calendar-day has-report" href="{site_url(route_for(by_date[iso]).removesuffix("index.html"), base_path)}" data-date="{iso}">{day.day}</a>')
                else:
                    rows.append(f'<span class="calendar-day" data-date="{iso}">{day.day}</span>')
        rows.append("</div></section>")
        result.append("\n".join(rows))
    return "\n".join(result)


def weekly_index(weeklies: list[dict], base_path: str = "") -> str:
    cards = []
    for report in sorted(weeklies, key=lambda item: item["week"], reverse=True):
        href = site_url(route_for(report).removesuffix("index.html"), base_path)
        cards.append(
            '<a class="weekly-link" href="%s"><span>%s</span><strong>%s</strong></a>'
            % (href, html.escape(report["week"]), html.escape(report["title"]))
        )
    return "".join(cards)


def build_calendar_page(dailies: list[dict], weeklies: list[dict], base_path: str = "") -> str:
    latest = max(dailies, key=lambda item: item["date"])
    latest_href = site_url(route_for(latest).removesuffix("index.html"), base_path)
    body = f'''<main class="archive-shell calendar-page">
  <section class="archive-heading"><p class="kicker">DAILY ARCHIVE</p><h1>日报日历</h1></section>
  <div class="calendar-layout">
    <div class="month-list">{calendar_cells(dailies, base_path)}</div>
    <aside class="calendar-side">
      <a class="selected-report" href="{latest_href}"><span>{latest['date']}</span><strong>{html.escape(latest['title'])}</strong><p>{html.escape(latest.get('summary', ''))}</p></a>
      <section class="weekly-rail"><p class="rail-label">周报索引</p>{weekly_index(weeklies, base_path)}</section>
    </aside>
  </div>
</main>'''
    return archive_shell(
        "日报日历｜美妆竞对情报",
        "calendar",
        body,
        f'<script src="{site_url("assets/site-calendar.js", base_path)}"></script>',
        base_path,
    )


def build_weekly_index_page(weeklies: list[dict], base_path: str = "") -> str:
    cards = []
    for report in sorted(weeklies, key=lambda item: item["week"], reverse=True):
        href = site_url(route_for(report).removesuffix("index.html"), base_path)
        cards.append(f'''<a class="week-card" href="{href}">
  <p>{html.escape(report['week'])}</p><h2>{html.escape(report['title'])}</h2><span>{html.escape(report.get('summary', ''))}</span>
</a>''')
    body = '<main class="archive-shell weekly-index"><section class="archive-heading"><p class="kicker">WEEKLY INSIGHTS</p><h1>周报</h1></section><section class="week-card-list">' + "\n".join(cards) + "</section></main>"
    return archive_shell("周报｜美妆竞对情报", "weekly", body, base_path=base_path)


def search_records(reports: list[dict], base_path: str = "") -> list[dict]:
    records = []
    for report in reports:
        records.append({
            "kind": report["kind"],
            "date": report.get("date", report.get("week")),
            "week": report.get("week", ""),
            "title": report["title"],
            "summary": report.get("summary", ""),
            "href": site_url(route_for(report).removesuffix("index.html"), base_path),
            "dimensions": report.get("dimensions", []),
            "brands": report.get("brands", []),
            "categories": report.get("categories", []),
            "channels": report.get("channels", []),
            "event_types": report.get("event_types", []),
        })
    return records


def build_search_page(reports: list[dict], base_path: str = "") -> str:
    records = search_records(reports, base_path)
    all_values = defaultdict(set)
    for record in records:
        for field in ("dimensions", "brands", "categories", "channels", "event_types"):
            all_values[field].update(record[field])
    selects = []
    labels = (("dimensions", "维度"), ("brands", "品牌"), ("categories", "赛道"), ("channels", "渠道"), ("event_types", "事件类型"))
    for field, label in labels:
        options = '<option value="">全部%s</option>' % label
        options += "".join('<option value="%s">%s</option>' % (html.escape(value), html.escape(value)) for value in sorted(all_values[field]))
        selects.append(f'<label><span>{label}</span><select data-filter="{field}">{options}</select></label>')
    safe_data = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    body = f'''<main class="archive-shell search-page">
  <section class="archive-heading"><p class="kicker">INTELLIGENCE SEARCH</p><h1>搜索</h1></section>
  <section class="search-panel"><label class="search-input"><span>关键词</span><input id="query" type="search" placeholder="搜索品牌、赛道、渠道或事件" /></label><div class="filter-row">{''.join(selects)}<label><span>日期</span><input id="report-date" type="date" /></label></div></section>
  <p class="search-count" id="search-count"></p><section class="search-results" id="search-results"></section>
</main>'''
    script = f'<script>window.__REPORTS__={safe_data};</script><script src="{site_url("assets/site-search.js", base_path)}"></script>'
    return archive_shell("搜索｜美妆竞对情报", "search", body, script, base_path)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prepare_hosted_output(public_dir: Path, hosted_project: Path) -> None:
    """Stage the validated static site in a small worker package for hosting."""
    if not (public_dir / "index.html").is_file():
        raise ValueError("Build the static site before preparing hosted output")
    worker_source = SITE_DIR / "internet/worker/index.js"
    if not worker_source.is_file():
        raise ValueError("Hosted worker source is missing")
    dist = hosted_project / "dist"
    static = hosted_project / "static"
    if static.exists():
        shutil.rmtree(static)
    shutil.copytree(public_dir, static)
    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(static, dist / "assets")
    (dist / "server").mkdir(parents=True, exist_ok=True)
    shutil.copy2(worker_source, dist / "server/index.js")


def build_site(root: Path, output: Path, base_path: str = "") -> None:
    """Build all public pages. The manifest is the single publication gate."""
    reports = load_manifest(root)
    dailies = [report for report in reports if report["kind"] == "daily"]
    weeklies = [report for report in reports if report["kind"] == "weekly"]
    if not dailies:
        raise ValueError("At least one published daily report is required")
    daily_routes = {item["date"]: site_url(route_for(item).removesuffix("index.html"), base_path) for item in dailies}

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copytree(ASSETS_DIR, output / "assets")

    for report in reports:
        source_file = root / report["source"]
        source = source_file.read_text(encoding="utf-8")
        active = "daily" if report["kind"] == "daily" else "weekly"
        route_path = output / route_for(report)
        pdf_href = ""
        if report.get("pdf"):
            pdf_name = Path(report["pdf"]).name
            (output / "pdf").mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / report["pdf"], output / "pdf" / pdf_name)
            pdf_href = site_url("pdf/" + pdf_name, base_path)
        write_file(
            route_path,
            decorate_report(source, active, report["source"], daily_routes, report.get("date", ""), pdf_href, base_path),
        )
        source_assets = source_file.parent / "assets"
        if source_assets.is_dir():
            shutil.copytree(source_assets, route_path.parent / "assets")

    latest_daily = max(dailies, key=lambda item: item["date"])
    latest_source = (root / latest_daily["source"]).read_text(encoding="utf-8")
    write_file(
        output / "index.html",
        decorate_report(
            latest_source,
            "daily",
            latest_daily["source"],
            daily_routes,
            latest_daily["date"],
            site_url("pdf/" + Path(latest_daily["pdf"]).name, base_path) if latest_daily.get("pdf") else "",
            base_path,
        ),
    )
    latest_assets = (root / latest_daily["source"]).parent / "assets"
    if latest_assets.is_dir():
        shutil.copytree(latest_assets, output / "assets", dirs_exist_ok=True)
    write_file(output / "calendar/index.html", build_calendar_page(dailies, weeklies, base_path))
    write_file(output / "weekly/index.html", build_weekly_index_page(weeklies, base_path))
    write_file(output / "search/index.html", build_search_page(reports, base_path))


if __name__ == "__main__":
    project_root = SITE_DIR.parent
    build_site(project_root, SITE_DIR / "public", os.environ.get("PAGES_BASE_PATH", "/beauty-intel"))
    prepare_hosted_output(SITE_DIR / "public", SITE_DIR / "internet")
    print("Built site/public from approved reports.")
