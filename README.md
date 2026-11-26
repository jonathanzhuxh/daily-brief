# Daily Brief · 新加坡早晚新闻与专题简报

每天 `08:00 SGT` 早报、`20:00 SGT` 晚报，由本机 **Antigravity 定时任务**生成并推送到本仓库，GitHub Actions 随后自动发布到 GitHub Pages。

## 在线访问
- **默认入口（自动展示最新一期，顶部可切换早/晚报）**：https://jonathanzhuxh.github.io/daily-brief/
- **早间简报直达**：https://jonathanzhuxh.github.io/daily-brief/morning.html
- **晚间简报直达**：https://jonathanzhuxh.github.io/daily-brief/evening.html

## 固定板块顺序
1. **气象状况**（今日天气、气温、24小时 PSI、1小时 PM2.5）
2. **本地重要新闻**（优先单列榜鹅 Punggol 社区动态）
3. **重大工程跟踪**
4. **军队动态跟踪**
5. **SpaceX动态跟踪**
6. **全球航天动态（排除SpaceX）**
7. **早晚专属板块**：早报 `小嶋阳菜动态` / 晚报 `金州勇士动态`（含 NBA Box Score）

## 文件结构
- `template/morning-template.html`、`template/evening-template.html`：早晚专属模板
- `morning.html`、`evening.html`：最新一期早报 / 晚报；`index.html` 为最近生成的那一期
- `memory/memory-log.md`：重大项目状态基线与跨期去重日志
- `.github/workflows/daily-brief.yml`：push 后发布 GitHub Pages

> 注意：需要在 `08:00` / `20:00` 时电脑开机并运行 Antigravity，定时任务才会触发。
