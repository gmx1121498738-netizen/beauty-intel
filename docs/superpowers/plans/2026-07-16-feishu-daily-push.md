# Feishu Daily Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send one Grace-approved summary of yesterday's published beauty daily report to a fixed Feishu group at 11:00 Asia/Shanghai, and stay silent when no eligible report exists.

**Architecture:** Extend the existing publication manifest with an optional reviewed `push` object. A standalone Python module selects yesterday's eligible report, builds a Feishu interactive card branded “美妆情报Bot”, signs and posts it to a group custom-bot webhook. GitHub Actions runs the module daily at 03:00 UTC and keeps all credentials in repository secrets.

**Tech Stack:** Python 3 standard library, `unittest`, Feishu custom-bot webhook, GitHub Actions.

---

## File structure

- `build.py`: validate optional push-review fields as part of the existing publication gate.
- `push_daily.py`: select a report, build the card, sign the request, and expose a safe CLI.
- `tests/test_build.py`: cover manifest validation for approved and invalid push records.
- `tests/test_push_daily.py`: cover silent skips, variable summaries, URLs, signatures, and webhook outcomes.
- `.github/workflows/push-feishu-daily.yml`: run at 11:00 Asia/Shanghai and allow dry-run/manual execution.
- `README.md`: document bot creation, secrets, approval fields, and test procedure.

### Task 1: Validate reviewed push data

**Files:**
- Modify: `tests/test_build.py`
- Modify: `build.py`

- [ ] **Step 1: Write failing manifest tests**

Add tests showing that `approved` requires a non-empty string list, that unsupported statuses fail, and that a valid variable-length summary passes:

```python
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
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_build -v`

Expected: the invalid push cases do not raise because validation is not implemented.

- [ ] **Step 3: Implement focused validation**

Add `validate_push(report)` in `build.py`. Allow `draft`, `approved`, and `disabled`; require `push` to be an object; require `items` to be a list of non-empty strings when approved; validate optional text fields as non-empty strings. Call it from `validate_manifest` for daily reports only.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest tests.test_build -v`

Expected: all site-build tests pass.

### Task 2: Select only yesterday's approved report

**Files:**
- Create: `tests/test_push_daily.py`
- Create: `push_daily.py`

- [ ] **Step 1: Write failing selection tests**

```python
def test_select_report_returns_only_approved_target_date(self):
    report = make_report("2026-07-15", "approved", ["重点一"])
    self.assertEqual(push_daily.select_report([report], "2026-07-15"), report)

def test_select_report_stays_silent_for_missing_or_draft_report(self):
    draft = make_report("2026-07-15", "draft", ["重点一"])
    self.assertIsNone(push_daily.select_report([draft], "2026-07-15"))
    self.assertIsNone(push_daily.select_report([], "2026-07-15"))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_push_daily -v`

Expected: import fails because `push_daily.py` does not exist.

- [ ] **Step 3: Implement date and eligibility selection**

Implement `shanghai_yesterday(now=None)` with `zoneinfo.ZoneInfo("Asia/Shanghai")` and `select_report(reports, target_date)`. Return `None` for no record or an ineligible record; raise `ValueError` for duplicate daily records on the target date.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest tests.test_push_daily -v`

Expected: selection and date tests pass.

### Task 3: Build the reviewed Feishu card

**Files:**
- Modify: `tests/test_push_daily.py`
- Modify: `push_daily.py`

- [ ] **Step 1: Write failing card tests**

Test that the card header is `美妆情报Bot｜7月15日日报`, every reviewed item appears once and in order, and the button points to `https://gmx1121498738-netizen.github.io/beauty-intel/daily/2026-07-15/`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tests.test_push_daily.FeishuCardTests -v`

Expected: fail because `build_card` is missing.

- [ ] **Step 3: Implement minimal interactive-card payload**

Implement `report_url(base_url, date)` and `build_card(report, base_url)`. Use `push.heading`, enumerate all `push.items`, and add one primary button using `push.detail_label` or `查看完整日报`. Escape user-controlled Markdown characters needed for reliable Feishu rendering.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest tests.test_push_daily.FeishuCardTests -v`

Expected: card tests pass.

### Task 4: Sign and send without exposing secrets

**Files:**
- Modify: `tests/test_push_daily.py`
- Modify: `push_daily.py`

- [ ] **Step 1: Write failing signature and response tests**

Use a fixed timestamp and secret to verify deterministic HMAC-SHA256/base64 output. Inject a small opener function so tests can inspect the JSON request without external network access. Test Feishu `code=0` as success and non-zero codes as a concise error that does not contain the webhook URL or secret.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_push_daily.FeishuWebhookTests -v`

Expected: fail because signing and sending functions are missing.

- [ ] **Step 3: Implement signing and webhook call**

Implement `feishu_signature(timestamp, secret)` and `send_webhook(webhook_url, card, secret="", opener=urlopen)`. Send UTF-8 JSON with a short timeout; add `timestamp` and `sign` only when a signing secret exists; parse and validate the Feishu JSON response.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest tests.test_push_daily.FeishuWebhookTests -v`

Expected: signature and webhook tests pass without a real request.

### Task 5: Add safe command-line behavior

**Files:**
- Modify: `tests/test_push_daily.py`
- Modify: `push_daily.py`

- [ ] **Step 1: Write failing CLI tests**

Test that default execution prints `SKIP` and returns zero for an absent report; `--dry-run --date YYYY-MM-DD` prints the card without requiring a webhook; and actual sending refuses to run when `FEISHU_WEBHOOK_URL` or `SITE_BASE_URL` is missing.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_push_daily.PushDailyCliTests -v`

Expected: fail because `main` is missing.

- [ ] **Step 3: Implement the CLI**

Support `--manifest`, `--date`, and `--dry-run`. Load `SITE_BASE_URL`, `FEISHU_WEBHOOK_URL`, and optional `FEISHU_WEBHOOK_SECRET` from the environment. Never print secret values. Return zero for silent skips and successful dry runs; return non-zero for invalid configuration or failed delivery.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest tests.test_push_daily -v`

Expected: all push tests pass.

### Task 6: Schedule at 11:00 and document setup

**Files:**
- Create: `.github/workflows/push-feishu-daily.yml`
- Modify: `tests/test_push_daily.py`
- Modify: `README.md`

- [ ] **Step 1: Write a failing workflow contract test**

Assert the workflow contains `cron: "0 3 * * *"`, `concurrency`, `SITE_BASE_URL`, `FEISHU_WEBHOOK_URL`, `FEISHU_WEBHOOK_SECRET`, and `python3 push_daily.py`.

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m unittest tests.test_push_daily.PushWorkflowTests -v`

Expected: fail because the workflow file does not exist.

- [ ] **Step 3: Add workflow and README instructions**

Configure `schedule` plus `workflow_dispatch` with a dry-run default. Set the production base URL to the GitHub Pages site. Document creating a fixed-group custom bot named `美妆情报Bot`, enabling signatures, adding repository secrets, reviewing `push.items`, and testing through a dry run before enabling real delivery.

- [ ] **Step 4: Run all tests and verify GREEN**

Run: `python3 -m unittest discover -s tests -v`

Expected: zero failures and zero errors.

### Task 7: Final verification and commit

**Files:**
- Verify all files above.

- [ ] **Step 1: Validate Python syntax and dry-run output**

Run: `python3 -m py_compile build.py push_daily.py`

Run: `SITE_BASE_URL=https://gmx1121498738-netizen.github.io/beauty-intel python3 push_daily.py --date 2026-07-15 --dry-run`

Expected: syntax succeeds; current 7月15日 record skips until its reviewed `push` block is added.

- [ ] **Step 2: Run the complete regression suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 3: Review the diff for credentials and scope**

Run: `git diff --check && git diff --stat && git grep -n "hooks.feishu.cn\|FEISHU_WEBHOOK_URL=" -- ':!docs/superpowers/plans/*'`

Expected: no whitespace failures, no actual webhook URL, and only the intended files changed.

- [ ] **Step 4: Commit the implementation**

```bash
git add build.py push_daily.py tests/test_build.py tests/test_push_daily.py .github/workflows/push-feishu-daily.yml README.md docs/superpowers/plans/2026-07-16-feishu-daily-push.md
git commit -m "Add reviewed Feishu daily push"
```
