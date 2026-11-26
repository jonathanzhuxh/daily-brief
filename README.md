# Daily Brief · 新加坡早晚新闻与专题简报（GitHub Actions 全云端版）

每日早晚自动在 **GitHub Actions 云端**生成的新加坡本地新闻与专题简报静态站点（每天 `08:02 SGT` 早报、`20:02 SGT` 晚报自动运行，**无需本地电脑开机**）。

## 在线访问
- **默认入口（自动展示最新一期，顶部可切换早/晚报）**：https://jonathanzhuxh.github.io/daily-brief/
- **早间简报直达**：https://jonathanzhuxh.github.io/daily-brief/morning.html
- **晚间简报直达**：https://jonathanzhuxh.github.io/daily-brief/evening.html

## 固定板块顺序
1. **气象状况**（顶部四项精简指标：今日天气、气温、24小时 PSI、1小时 PM2.5）
2. **本地重要新闻**（新加坡本地主流媒体，优先单列榜鹅 Punggol 社区动态）
3. **重大工程跟踪**（MRT/LRT、NSC、巴士车队、PLAB 迁移、长岛、南部濒水区、大士港等）
4. **军队动态跟踪**（新加坡武装部队陆海空装备采购、升级与演训动态）
5. **SpaceX动态跟踪**（Falcon / Dragon 发射回收及 Starship / Raptor / 基地技术深挖）
6. **全球航天动态（排除SpaceX）**（Blue Origin、Rocket Lab、ULA、NASA、ESA、JAXA、商业及国际航天动态）
7. **早晚专属板块**：
   - 早报（`template/morning-template.html`）：**小嶋阳菜动态**
   - 晚报（`template/evening-template.html`）：**金州勇士动态**（含标准 NBA Box Score 技术统计表）

## 云端密钥与手动触发说明
- **仓库加密密钥（Repository Secret）**：在仓库 `Settings → Secrets and variables → Actions` 中配置 `GEMINI_API_KEY`。
- **手动触发**：打开仓库 `Actions → Daily Brief (Cloud Schedule & Pages Deploy) → Run workflow`，可随时选择 `auto` / `morning` / `evening` 立即在云端运行生成。
