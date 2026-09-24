# Embodied AI Paper Radar

一个无需前端手动 fetch 的论文推送网页：定时任务每天从 arXiv 拉取最新论文，脚本自动分类并生成 `data/papers.json`，网页直接读取这个静态 JSON 展示标题、摘要、关键词和链接。

## 功能

- 每日自动更新：`.github/workflows/update-papers.yml` 默认每天北京时间 08:20 运行。
- 自动分类：`Manipulation`、`Vision-Language-Action`、`UAV`、`Humanoid`。
- 前端展示：支持分类标签、全文搜索、论文摘要、关键词、arXiv / PDF 链接、作者信息。
- 零后端部署：可直接用 GitHub Pages / Nginx / 任意静态托管。

## 本地预览

```bash
cd paper-radar
python3 -m http.server 8000
```

浏览器打开 `http://localhost:8000`。

## 手动生成一次数据

如果想在本地先看真实数据，运行：

```bash
cd paper-radar
python3 scripts/fetch_papers.py --output data/papers.json --days 14 --per-category 45 --limit 140 --fail-when-stale
```

脚本只使用 Python 标准库，不需要安装依赖。

## 抓取异常与验证

- 收到 HTTP 406 时，脚本会在等待后改用 arXiv 官方支持的 POST 查询，保留相同的关键词、排序和数量限制。HTTP 429 仍按 `Retry-After` 或指数退避重试。
- 自动更新启用 `--fail-when-stale`：任一分类抓取失败，或过滤后没有近期论文时，保留原有 JSON 和更新时间，并让 Actions 明确失败，防止“绿色运行但持续停更”或不完整数据覆盖。
- 本地省略该参数时，全部抓取失败仍可保留旧文件并正常退出；不建议在定时任务中省略。
- 抓取脚本、测试或更新 workflow 推送到 `main` 后会立即运行一次更新；手动更新仍可通过 `Actions -> Update Papers -> Run workflow` 触发。
- 查看 `Fetch latest arXiv papers` 日志中的各分类数量，并确认网站更新时间。任务失败时，网站继续展示上次成功的数据。

运行回归测试：

```bash
python3 -m unittest discover -s tests -v
```

## 部署到 GitHub Pages

1. 将 `paper-radar` 目录内容推到一个 GitHub 仓库。
2. 进入仓库 `Settings -> Actions -> General`，确保 workflow 有写入权限。
3. 进入仓库 `Settings -> Pages`，将 Source 设为 `GitHub Actions`，由 `Deploy Pages` workflow 发布。
4. 打开 `Actions -> Update Papers`，可先点 `Run workflow` 触发第一次更新。

之后 GitHub Actions 会每天更新 `data/papers.json` 并自动提交，网页刷新即可看到新论文。

## 调整分类关键词

编辑 `scripts/fetch_papers.py` 里的 `CATEGORIES`：

- `query_terms` 控制从 arXiv 搜索什么。
- `keywords` 控制卡片展示关键词与分类打分。
- `color` 控制该分类卡片强调色。

## 常见修改

- 更新频率：修改 `.github/workflows/update-papers.yml` 中的 `cron`。
- 保留天数：修改 workflow 命令里的 `--days 14`。
- 每类抓取数量：修改 `--per-category 45`。
- 最多展示数量：修改 `--limit 140`。
