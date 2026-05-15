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
python3 scripts/fetch_papers.py --output data/papers.json --days 14 --per-category 45 --limit 140
```

脚本只使用 Python 标准库，不需要安装依赖。

## 部署到 GitHub Pages

1. 将 `paper-radar` 目录内容推到一个 GitHub 仓库。
2. 进入仓库 `Settings -> Actions -> General`，确保 workflow 有写入权限。
3. 进入 `Settings -> Pages`，选择从 `main` 分支的根目录发布。
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
