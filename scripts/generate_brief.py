#!/usr/bin/env python3
"""Cloud generator for Singapore Morning & Evening Daily Brief via Gemini Interactions API."""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from google import genai
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "template"
MEMORY_LOG_PATH = REPO_ROOT / "memory" / "memory-log.md"
SGT = ZoneInfo("Asia/Singapore")

REDIRECT_URL_RE = re.compile(
    r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[A-Za-z0-9_-]+={0,2}"
)
LI_WRAPPER_RE = re.compile(r"^\s*<li[^>]*>(.*)</li>\s*$", re.IGNORECASE | re.DOTALL)


class SourceItem(BaseModel):
    publisher: str = Field(description="媒体或官方机构名称，如 'The Straits Times'、'CNA'、'Space.com'、'PR TIMES'")
    title: str = Field(description="原始报道或页面标题")
    url: str = Field(description="原始报道或官方页面的完整 HTTPS URL")


class HltTableRow(BaseModel):
    channel_html: str = Field(
        description="渠道或单品名称（可包含指向该渠道公开页面的 <a href='...' target='_blank' rel='noopener noreferrer'> 链接）"
    )
    metric_num: str = Field(description="关键数字或累计评价数，如 '679'、'89'、'322'")
    summary_text: str = Field(description="近期动态与消费者真实风评摘要（纯文本）")


class GswBoxScoreRow(BaseModel):
    player: str = Field(description="球员姓名（如 '斯蒂芬·库里（Stephen Curry）'，全队汇总行填 '全队合计（Totals）'）")
    min: str = Field(description="上场时间 MIN（缺阵填 'DNP'，无单场数据填 '—'）")
    pts: str = Field(description="得分 PTS")
    reb: str = Field(description="篮板 REB")
    ast: str = Field(description="助攻 AST")
    fg: str = Field(description="投篮命中-出手或命中率 FG，如 '9-18' 或 '50.0%'")
    three_pt: str = Field(description="三分命中-出手或命中率 3PT，如 '5-11' 或 '45.5%'")
    plus_minus: str = Field(description="正负值 +/-，如 '+12'、'-4' 或 '—'")
    note: str = Field(description="场上表现亮点、技战术作用或伤病状态备注（纯文本）")
    is_totals_row: bool = Field(default=False, description="是否为最后一行全队合计行")


class BaseBriefPayload(BaseModel):
    weather_condition: str = Field(description="一句极简天气状况，如 '午后雷阵雨'、'多云有雨'、'局部阵雨'")
    temp_range: str = Field(description="气温范围，如 '24.0 – 32.0 °C'")
    psi_range: str = Field(description="24小时 PSI 范围，如 '28 – 52'")
    pm25_range: str = Field(description="1小时 PM2.5 范围，如 '4 – 14 µg/m³'")
    local_news_items: List[str] = Field(
        description="本地重要新闻列表。每项为单条 <li> 内部的 HTML 内容（不含外层 <li> 标签），格式如 '<strong>事件标题：</strong>关键事实与数字。（<a href=\"...\" target=\"_blank\" rel=\"noopener noreferrer\">CNA</a>）'。榜鹅 Punggol 新闻须优先单列。"
    )
    infra_items: List[str] = Field(
        description="重大工程跟踪列表（MRT/LRT、NSC、巴士车队、PLAB迁移、长岛、南部濒水区、大士港等）。无新增则填 1 条 '<strong>暂无新增动态：</strong>...'"
    )
    saf_items: List[str] = Field(
        description="军队动态跟踪列表（SAF 陆军装甲车/枪械、海军军舰、空军战机采购列装与演训）。无新增则填 1 条 '<strong>暂无新增动态：</strong>...'"
    )
    spacex_items: List[str] = Field(
        description="SpaceX动态跟踪列表（仅限 SpaceX：Falcon/Dragon 发射回收及 Starship 箭体迭代、Raptor 发动机、低温/静态点火、塔架及 Starbase/德州/佛州/路易斯安那设施进展）。未经完全证实的爱好者/社媒消息须附 '<span class=\"tag-unverified\">[未经证实，仅供参考]</span>'。"
    )
    global_space_items: List[str] = Field(
        description="全球航天动态（排除SpaceX）列表（Blue Origin、Rocket Lab、ULA、NASA、ESA、JAXA、ISRO 等全球重要发射与商业航天进展，不含纯 SpaceX 内容）。无新增则填 1 条 '<strong>暂无新增动态：</strong>...'"
    )
    sources: List[SourceItem] = Field(description="按正文引用顺序排列的全部原始信源列表")
    updated_memory_log_markdown: str = Field(
        description="更新后的完整 memory-log.md Markdown 全文：保留并更新『一、重大项目与长期追踪当前状态基线』，并在『二、近期已播报新闻记录』中仅保留最近两期（上一期 + 本期）去重记录，清理更早流水。"
    )


class MorningBriefPayload(BaseBriefPayload):
    hlt_items: List[str] = Field(
        description="早报专属：小嶋阳菜动态列表（个人社媒、Her lip to / BEAUTY / ROSIER 动态、经营并购及消费者真实风评深度分析）。每项为 <li> 内部 HTML。"
    )
    hlt_table_rows: List[HltTableRow] = Field(
        description="早报专属：日本美妆/电商渠道或核心单品口碑追踪数据行（至少 2-4 行，如 @cosme、乐天官方店等）"
    )
    hlt_table_caption: str = Field(description="表格底部说明，如 '数据截至 YYYY年M月D日各平台公开页面。'")


class EveningBriefPayload(BaseBriefPayload):
    gsw_matchup_summary: str = Field(
        description="晚报专属：一行概括金州勇士最新赛果（或赛前对阵）、当前战绩与下一场赛程"
    )
    gsw_items: List[str] = Field(
        description="晚报专属：金州勇士比赛复盘、轮换调整、防守策略、库里与伦德伯格等核心球员技术细节及伤病/交易动态列表（每项为 <li> 内部 HTML）"
    )
    gsw_boxscore_title: str = Field(
        description="晚报专属：Box Score 表头括号说明，如 'GSW vs SAC · 2026-11-25' 或 '核心轮换赛季场均与伤病状态'"
    )
    gsw_boxscore_rows: List[GswBoxScoreRow] = Field(
        description="晚报专属：主要球员技术统计行（上场时间、得分、篮板、助攻、投篮、三分、正负值及备注）"
    )
    gsw_boxscore_caption: str = Field(description="表格底部数据来源与比赛日期说明")


def resolve_redirect_url(url: str, cache: dict[str, str]) -> str:
    if url in cache:
        return cache[url]
    resolved = url
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DailyBriefBot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                final_url = resp.geturl()
                if final_url and "grounding-api-redirect" not in final_url:
                    resolved = final_url
                    break
        except Exception:
            continue
    cache[url] = resolved
    return resolved


def replace_redirect_urls(text: str, cache: dict[str, str]) -> str:
    return REDIRECT_URL_RE.sub(lambda m: resolve_redirect_url(m.group(0), cache), text)


def format_li_items(items: list[str], indent: str = "        ") -> str:
    if not items:
        items = ["<strong>暂无新增动态：</strong>本时间窗口内暂无新增官方或主流媒体通报。"]
    cleaned: list[str] = []
    for raw in items:
        item = raw.strip()
        m = LI_WRAPPER_RE.match(item)
        if m:
            item = m.group(1).strip()
        if item:
            cleaned.append(f"{indent}<li>{item}</li>")
    return "\n".join(cleaned)


def format_sources(sources: list[SourceItem]) -> str:
    lines: list[str] = []
    for src in sources:
        pub = html.escape(src.publisher.strip(), quote=False)
        title = html.escape(src.title.strip(), quote=False)
        url = html.escape(src.url.strip(), quote=True)
        lines.append(
            f'      <li>{pub} — <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></li>'
        )
    return "\n".join(lines)


def build_prompt(edition: str, now_sgt: datetime, memory_md: str) -> tuple[str, str, str]:
    today_cn = f"{now_sgt.year}年{now_sgt.month}月{now_sgt.day}日"
    gen_hm = now_sgt.strftime("%H:%M")

    if edition == "morning":
        prev_day = now_sgt - timedelta(days=1)
        prev_cn = f"{prev_day.year}年{prev_day.month}月{prev_day.day}日"
        end_hm = "08:00" if 7 <= now_sgt.hour <= 9 else gen_hm
        title = f"新加坡早间新闻与专题简报 · {today_cn}"
        common_window = f"{prev_cn} 20:00 – {now_sgt.month}月{now_sgt.day}日 {end_hm} SGT"
        special_window = f"{prev_cn} 08:00 – {today_cn} {end_hm} SGT（过去 24 小时）"
        special_instructions = f"""- **7) 小嶋阳菜动态**（早报专属，日文媒体优先，强化风评深度，时间范围：{special_window}，严禁出现 NBA 内容）：
  汇总小嶋阳菜个人社媒最新动态、Her lip to（含 Her lip to BEAUTY / ROSIER）最新动态与财报/经营状态，并重点深挖消费者与舆论对产品、品牌及小嶋阳菜本人的真实风评与评价（如 @cosme、乐天官方店、LIPS、PR TIMES 等公开评价与报道），同时提供结构化口碑追踪表格数据行。"""
    else:
        end_hm = "20:00" if 19 <= now_sgt.hour <= 21 else gen_hm
        prev_day = now_sgt - timedelta(days=1)
        prev_cn = f"{prev_day.year}年{prev_day.month}月{prev_day.day}日"
        title = f"新加坡晚间新闻与专题简报 · {today_cn}"
        common_window = f"{today_cn} 08:00 – {end_hm} SGT"
        special_window = f"{prev_cn} 20:00 – {today_cn} {end_hm} SGT（过去 24 小时）"
        special_instructions = f"""- **7) 金州勇士动态**（晚报专属，英文媒体优先，强化数据与技战术深度，时间范围：{special_window}，严禁出现小嶋阳菜内容）：
  汇总金州勇士队最新比赛结果、球队伤病/轮换/交易动态，深入梳理赛后技战术与风格点评（轮换调整、防守策略、库里与伦德伯格等核心球员的技术细节与表现），并提供完整准确的球员技术统计表（MIN、PTS、REB、AST、FG、3PT、+/- 与表现备注；若过去 24 小时无比赛，填入核心轮换赛季场均数据及最新伤病状态）。"""

    time_window_line = f"信息窗口：{common_window} · 生成时间：{gen_hm} SGT"

    prompt = f"""当前新加坡时间（SGT / UTC+8）为：{now_sgt.strftime('%Y-%m-%d %H:%M SGT')}。
请使用 Google Search 实时检索并核实最新报道，为我生成《{title}》的结构化数据，并同步生成更新后的记忆去重日志。

### 一、本次检索时间窗口与去重基准
- 公共板块（本地重要新闻、重大工程跟踪、军队动态跟踪、SpaceX动态跟踪、全球航天动态）严格限定窗口：**{common_window}**。
- 首先仔细阅读以下《Daily Brief Memory Log》，掌握各专题最新状态基线与近期已播报条目，严格去重并杜绝把已发生的旧闻（尤其是 SpaceX 历史发射/测试）误作新进展：

<memory_log>
{memory_md}
</memory_log>

### 二、内部信源与语言规范（严格执行，但切勿将排除说明或去重说明等元信息写进简报正文）
1. 所有资讯优先参考英文媒体（早报小嶋阳菜板块优先参考日文媒体）。
2. **明确排除所有来自中国大陆和香港的英文媒体**（如 CGTN、China Daily、Global Times、SCMP、Xinhua 等）；参考中文资料时同样**明确排除中国大陆媒体及法轮功媒体**（若全球航天板块涉及中国航天发射等国际事件，仅可引述 Space.com、SpaceNews、Aviation Week、NASA 等国际英文主流/专业媒体）。
3. 交通、基础设施、军事、航天（SpaceX 及全球航天）及小嶋阳菜相关信息，可引述爱好者网站或社交媒体账号中未经完全证实的消息，但须在对应条目旁附上 `<span class="tag-unverified">[未经证实，仅供参考]</span>`。
4. 严格核对每条新闻与数据的发布时间戳；若某板块在目标时段内确无新动态，直接返回一条 `<strong>暂无新增动态：</strong>...` 说明，绝不拼凑旧闻。
5. 每条有实质新闻的 `<li>` 内部 HTML 以 `<strong>精炼标题：</strong>具体事实与关键数字。（<a href="真实原始URL" target="_blank" rel="noopener noreferrer">媒体名</a>）` 编写，并在 `sources` 数组中完整列出对应信源。

### 三、按固定顺序检索并整理的 7 个板块
- **1) 气象状况**：检索新加坡气象署（MSS / NEA）及 Haze.sg 当日最新数据，仅提取 4 项精简指标：一句简短今日天气、气温范围、24小时 PSI、1小时 PM2.5。
- **2) 本地重要新闻**：仅参考新加坡本地主流媒体（The Straits Times、CNA、TODAY 及 PUB/LTA/SPF 等政府机构通报）。重要政治、民生、司法、社区及文体事件**禁止合并报道**，每件独立事件单独成条；**榜鹅（Punggol）**相关社区新闻须优先并单独列出。
- **3) 重大工程跟踪**：独立汇总新加坡 MRT/LRT 建设（跨岛线、实里达线、登加线、裕廊区域线、TEL/DTL 等）、南北交通廊道（NSC）、巴士车队更新、巴耶利峇空军基地（PLAB）迁移、长岛计划、南部濒水区及大士港等最新建设与规划动态。
- **4) 军队动态跟踪**：独立汇总新加坡武装部队（SAF / MINDEF）陆军装甲车与枪械、海军军舰、空军战机等最新采购、列装、升级或演训装备动态。
- **5) SpaceX动态跟踪**（仅限 SpaceX，强化技术深度）：汇总猎鹰 9 号 / 重型猎鹰 / 龙飞船（Falcon / Dragon）最新发射、返回与回收动态及近期排期，并**重点深挖 Starship 技术进展**（下一次发射安排、Block 3 / Block 4 等箭体版本迭代、Raptor 发动机测试与升级如 Raptor 3、箭体与助推器低温压力/静态点火测试、运输动态、发射台与捕获塔架改造，以及 Starbase、Massey's/McGregor 德州研发测试设施、佛州 LC-39A / SLC-37、路易斯安那等设施建设与封路通告动态）。
- **6) 全球航天动态（排除SpaceX）**：汇总除 SpaceX 以外的全球重要航天发射、运载器研发、深空探测与商业航天动态（如 Blue Origin New Glenn、Rocket Lab Electron/Neutron、ULA Vulcan、NASA Artemis、ESA/Ariane、JAXA、ISRO、国际空间站及其他各国重要发射与商业合同；纯 SpaceX 内容归入第 5 板块，不在此重复）。
{special_instructions}

### 四、更新记忆日志（`updated_memory_log_markdown`）
- 输出完整更新后的 Markdown：第一部分保留并刷新各重大项目最新状态基线（防过时误报），第二部分仅保留**最近两期**（上一期 + 本期 `{common_window}`）已播报新闻摘要与链接，清理更早期的历史流水记录。
"""
    return title, time_window_line, prompt


def render_morning_html(
    template: str, title: str, time_window: str, payload: MorningBriefPayload
) -> str:
    rows_html: list[str] = []
    for row in payload.hlt_table_rows:
        rows_html.append(
            "          <tr>\n"
            f"            <td>{row.channel_html.strip()}</td>\n"
            f'            <td class="num">{html.escape(row.metric_num.strip(), quote=False)}</td>\n'
            f'            <td class="note">{html.escape(row.summary_text.strip(), quote=False)}</td>\n'
            "          </tr>"
        )
    replacements = {
        "{{TITLE}}": html.escape(title, quote=False),
        "{{TIME_WINDOW}}": html.escape(time_window, quote=False),
        "{{WEATHER_CONDITION}}": html.escape(payload.weather_condition.strip(), quote=False),
        "{{TEMP_RANGE}}": html.escape(payload.temp_range.strip(), quote=False),
        "{{PSI_RANGE}}": html.escape(payload.psi_range.strip(), quote=False),
        "{{PM25_RANGE}}": html.escape(payload.pm25_range.strip(), quote=False),
        "{{LOCAL_NEWS_ITEMS}}": format_li_items(payload.local_news_items),
        "{{INFRA_ITEMS}}": format_li_items(payload.infra_items),
        "{{SAF_ITEMS}}": format_li_items(payload.saf_items),
        "{{SPACEX_ITEMS}}": format_li_items(payload.spacex_items),
        "{{GLOBAL_SPACE_ITEMS}}": format_li_items(payload.global_space_items),
        "{{HLT_ITEMS}}": format_li_items(payload.hlt_items, indent="          "),
        "{{HLT_TABLE_ROWS}}": "\n".join(rows_html),
        "{{HLT_TABLE_CAPTION}}": html.escape(payload.hlt_table_caption.strip(), quote=False),
        "{{SOURCES_ITEMS}}": format_sources(payload.sources),
    }
    out = template
    for key, val in replacements.items():
        out = out.replace(key, val)
    return out


def render_evening_html(
    template: str, title: str, time_window: str, payload: EveningBriefPayload
) -> str:
    rows_html: list[str] = []
    for row in payload.gsw_boxscore_rows:
        tr_open = '<tr class="totals">' if row.is_totals_row else "<tr>"
        rows_html.append(
            f"          {tr_open}\n"
            f"            <td>{html.escape(row.player.strip(), quote=False)}</td>\n"
            f'            <td class="num">{html.escape(row.min.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.pts.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.reb.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.ast.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.fg.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.three_pt.strip(), quote=False)}</td>\n'
            f'            <td class="num">{html.escape(row.plus_minus.strip(), quote=False)}</td>\n'
            f'            <td class="note">{html.escape(row.note.strip(), quote=False)}</td>\n'
            "          </tr>"
        )
    replacements = {
        "{{TITLE}}": html.escape(title, quote=False),
        "{{TIME_WINDOW}}": html.escape(time_window, quote=False),
        "{{WEATHER_CONDITION}}": html.escape(payload.weather_condition.strip(), quote=False),
        "{{TEMP_RANGE}}": html.escape(payload.temp_range.strip(), quote=False),
        "{{PSI_RANGE}}": html.escape(payload.psi_range.strip(), quote=False),
        "{{PM25_RANGE}}": html.escape(payload.pm25_range.strip(), quote=False),
        "{{LOCAL_NEWS_ITEMS}}": format_li_items(payload.local_news_items),
        "{{INFRA_ITEMS}}": format_li_items(payload.infra_items),
        "{{SAF_ITEMS}}": format_li_items(payload.saf_items),
        "{{SPACEX_ITEMS}}": format_li_items(payload.spacex_items),
        "{{GLOBAL_SPACE_ITEMS}}": format_li_items(payload.global_space_items),
        "{{GSW_MATCHUP_SUMMARY}}": html.escape(payload.gsw_matchup_summary.strip(), quote=False),
        "{{GSW_ITEMS}}": format_li_items(payload.gsw_items, indent="          "),
        "{{GSW_BOXSCORE_TITLE}}": html.escape(payload.gsw_boxscore_title.strip(), quote=False),
        "{{GSW_BOXSCORE_ROWS}}": "\n".join(rows_html),
        "{{GSW_BOXSCORE_CAPTION}}": html.escape(payload.gsw_boxscore_caption.strip(), quote=False),
        "{{SOURCES_ITEMS}}": format_sources(payload.sources),
    }
    out = template
    for key, val in replacements.items():
        out = out.replace(key, val)
    return out


def run_background_interaction(
    client: genai.Client, model: str, prompt: str, schema: dict
) -> str:
    start_ts = time.monotonic()
    interaction = client.interactions.create(
        model=model,
        input=prompt,
        background=True,
        tools=[{"type": "google_search"}],
        generation_config={"thinking_level": "medium"},
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
    )
    interaction_id = interaction.id
    print(f"Started background interaction: {interaction_id} (status={interaction.status})", flush=True)

    try:
        while interaction.status in ("in_progress", "queued"):
            time.sleep(5)
            interaction = client.interactions.get(id=interaction_id)
            elapsed = int(time.monotonic() - start_ts)
            n_steps = len(getattr(interaction, "steps", None) or [])
            print(f"[+{elapsed}s] status={interaction.status} steps={n_steps}", flush=True)
            if elapsed > 420:
                raise TimeoutError(f"Interaction {interaction_id} exceeded 420s")

        if interaction.status != "completed":
            err_detail = getattr(interaction, "error", None)
            raise RuntimeError(f"Interaction ended with status={interaction.status}, error={err_detail}")

        usage = getattr(interaction, "usage", None)
        if usage is not None:
            print(f"Completed in {int(time.monotonic() - start_ts)}s | usage={usage}", flush=True)

        if not interaction.output_text:
            raise RuntimeError("Interaction completed with empty output_text")
        return interaction.output_text
    finally:
        try:
            client.interactions.delete(id=interaction_id)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Morning or Evening Daily Brief.")
    parser.add_argument(
        "--edition",
        choices=["auto", "morning", "evening"],
        default="auto",
        help="Which edition to generate ('auto' selects by current Asia/Singapore hour).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.", file=sys.stderr, flush=True)
        return 1

    now_sgt = datetime.now(SGT)
    edition = args.edition
    if edition == "auto":
        edition = "morning" if now_sgt.hour < 14 else "evening"

    model = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen").strip() or "gemini-4-hydrogen"
    print(f"Generating {edition} brief at {now_sgt.isoformat()} using model '{model}'...", flush=True)

    memory_md = MEMORY_LOG_PATH.read_text(encoding="utf-8")
    template_path = TEMPLATE_DIR / f"{edition}-template.html"
    template_html = template_path.read_text(encoding="utf-8")

    title, time_window, prompt = build_prompt(edition, now_sgt, memory_md)
    schema_cls = MorningBriefPayload if edition == "morning" else EveningBriefPayload

    client = genai.Client(api_key=api_key)
    raw_json = run_background_interaction(client, model, prompt, schema_cls.model_json_schema())

    url_cache: dict[str, str] = {}
    if edition == "morning":
        payload_m = MorningBriefPayload.model_validate_json(raw_json)
        rendered_html = render_morning_html(template_html, title, time_window, payload_m)
        new_memory = payload_m.updated_memory_log_markdown.strip()
        target_html_path = REPO_ROOT / "morning.html"
    else:
        payload_e = EveningBriefPayload.model_validate_json(raw_json)
        rendered_html = render_evening_html(template_html, title, time_window, payload_e)
        new_memory = payload_e.updated_memory_log_markdown.strip()
        target_html_path = REPO_ROOT / "evening.html"

    rendered_html = replace_redirect_urls(rendered_html, url_cache)
    if "{{" in rendered_html:
        raise RuntimeError("Unresolved '{{...}}' placeholder detected in rendered HTML!")

    target_html_path.write_text(rendered_html, encoding="utf-8")
    shutil.copyfile(target_html_path, REPO_ROOT / "index.html")

    if new_memory.startswith("#"):
        new_memory = replace_redirect_urls(new_memory, url_cache)
        MEMORY_LOG_PATH.write_text(new_memory + "\n", encoding="utf-8")
    else:
        print("WARNING: updated_memory_log_markdown did not start with '#', keeping existing header.", file=sys.stderr, flush=True)

    print(f"Successfully updated {target_html_path.name}, index.html, and memory/memory-log.md.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
