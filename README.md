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
