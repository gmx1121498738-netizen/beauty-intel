# 美妆竞对情报站点

这是一个纯静态站点：日报与周报正文直接使用已确认的 HTML 成品；`site/data/published.json` 是唯一的发布清单。草稿、Markdown 初稿与未确认内容不会进入站点。

## 本地预览

```bash
python3 site/publish.py
python3 -m http.server 8080 --directory site/public
```

在浏览器打开 `http://localhost:8080`。首页会自动取清单中日期最新的日报 HTML，完整保留日报卡片、图片、来源和信号判断。

## 确认发布一篇日报

1. 先由 Grace 确认日报 HTML 成品已定稿。
2. 在 `site/data/published.json` 追加该 HTML 的路径与检索字段。
3. 运行 `python3 site/publish.py`。

不要把 Markdown 初稿、未确认 HTML 或临时下载文件写入清单。

## 飞书定时推送

固定群机器人名称统一为 **美妆情报Bot**。每天北京时间 11:00，任务只检查前一自然日：日报已经发布且群消息经过 Grace 审核时发送；没有日报、仍在审核或明确停用时保持安静。

### 创建群机器人

1. 在目标飞书群打开“设置 → 群机器人 → 添加机器人 → 自定义机器人”。
2. 名称填写“美妆情报Bot”，描述可填写“推送已审核的美妆竞对情报日报与行业洞察”。
3. 在安全设置中启用“签名校验”。
4. 分别保存 Webhook 地址和签名密钥，不要粘贴到代码、文档或群聊中。
5. 在 GitHub 仓库打开“Settings → Secrets and variables → Actions”，添加：
   - `FEISHU_WEBHOOK_URL`：群机器人的完整 Webhook 地址；
   - `FEISHU_WEBHOOK_SECRET`：签名校验密钥。

### 审核群消息

Grace 通知正式发布日报时，先为对应日报生成 `push` 预览：

```json
"push": {
  "status": "draft",
  "heading": "昨日重点",
  "items": [
    "第一条待审核摘要。",
    "第二条待审核摘要。"
  ],
  "detail_label": "查看完整日报"
}
```

摘要数量根据当天内容决定。Grace 审核文字后，将 `status` 改为 `approved`；机器人只发送清单中这版文字，不会在发送当天重新调用 AI 总结。若不推送该日报，将状态改为 `disabled`。

### 测试与发送

- 本地预览指定日期，不发送消息：

  ```bash
  SITE_BASE_URL=https://gmx1121498738-netizen.github.io/beauty-intel \
    python3 push_daily.py --date 2026-07-15 --dry-run
  ```

- GitHub Actions 中可以手动运行“Push approved daily to Feishu”。`dry_run` 默认为开启，只生成预览；关闭后才会真实发送。
- 自动任务使用 `0 3 * * *`，即北京时间每天 11:00。昨日没有 `approved` 日报时，任务显示 `SKIP` 并正常结束。
- 次日 11:00 后才完成审核的消息不会自动补发。确需补发时，应手动选择日期，并在发送前再次确认。

飞书卡片使用官方自定义机器人签名算法。凭据只由 GitHub Secrets 注入，程序日志不会输出 Webhook 或签名密钥。
