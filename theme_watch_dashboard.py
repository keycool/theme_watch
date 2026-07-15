from __future__ import annotations

import csv
from datetime import datetime
from html import escape
from pathlib import Path

from theme_watch_config import CORRELATION_DIR, TOPIC_PAGES


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "theme_watch"
OUTPUT_HTML = REPORT_DIR / "index.html"


BASE_CARDS = [
    {"bucket": "科技成长与高端制造", "code": "512480.SH", "name": "半导体 ETF", "href": "pages/theme_512480_sw_l2_watch_report.html"},
    {"bucket": "科技成长与高端制造", "code": "515790.SH", "name": "光伏 ETF", "href": "pages/theme_515790_sw_l2_watch_report.html"},
    {"bucket": "科技成长与高端制造", "code": "515230.SH", "name": "软件 ETF", "href": "pages/theme_515230_software_watch_report.html"},
    {"bucket": "科技成长与高端制造", "code": "159998.SZ", "name": "计算机 ETF", "href": "pages/theme_159998_computer_watch_report.html"},
    {"bucket": "大消费与医药", "code": "512980.SH", "name": "传媒 ETF", "href": "pages/theme_512980_sw_l2_watch_report.html"},
    {"bucket": "科技成长与高端制造", "code": "931994.CSI", "name": "电网设备主题指数", "href": "pages/theme_931994_sw_l2_watch_report.html"},
    {
        "bucket": "科技成长与高端制造",
        "code": "TMT-COMM",
        "name": "通信链条对照组",
        "href": "pages/theme_communication_compare_report.html",
        "status": "对照观察",
        "map": "通信设备、通信服务",
        "note": "对照页不走 ETF 相关性 CSV，保留人工定义入口。",
    },
    {"bucket": "大消费与医药", "code": "159928.SZ", "name": "消费 ETF", "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html"},
    {"bucket": "大消费与医药", "code": "512690.SH", "name": "酒 ETF", "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html"},
    {"bucket": "大消费与医药", "code": "512010.SH", "name": "医药 ETF", "href": "pages/theme_512010_medicine_watch_report.html"},
    {"bucket": "大消费与医药", "code": "512170.SH", "name": "医疗 ETF", "href": "pages/theme_512170_healthcare_watch_report.html"},
    {"bucket": "大消费与医药", "code": "159992.SZ", "name": "创新药 ETF", "href": "pages/theme_159992_innovative_drug_watch_report.html"},
    {"bucket": "大消费与医药", "code": "159996.SZ", "name": "家电 ETF", "href": "pages/theme_159996_sw_l2_watch_report.html"},
    {"bucket": "周期资源", "code": "159930.SZ", "name": "能源 ETF", "href": "pages/theme_cycle_resources_sw_l2_watch_report.html"},
    {"bucket": "周期资源", "code": "159697.SZ", "name": "石油 ETF", "href": "pages/theme_cycle_resources_sw_l2_watch_report.html"},
    {"bucket": "周期资源", "code": "515220.SH", "name": "煤炭 ETF", "href": "pages/theme_cycle_resources_sw_l2_watch_report.html"},
    {"bucket": "周期资源", "code": "159870.SZ", "name": "化工 ETF", "href": "pages/theme_159870_chemical_compare_report.html"},
    {"bucket": "红利金融地产", "code": "515180.SH", "name": "易方达红利 ETF", "href": "pages/theme_515180_sw_l2_watch_report.html"},
    {"bucket": "红利金融地产", "code": "512890.SH", "name": "红利低波 ETF", "href": "pages/theme_512890_sw_l2_watch_report.html"},
    {"bucket": "红利金融地产", "code": "512880.SH", "name": "证券 ETF", "href": "pages/theme_512880_sw_l2_watch_report.html"},
    {"bucket": "红利金融地产", "code": "512200.SH", "name": "房地产 ETF", "href": "pages/theme_512200_real_estate_watch_report.html"},
]


DISPLAY_ORDER = {
    "512010.SH": 10,
    "512170.SH": 11,
    "159992.SZ": 12,
    "159928.SZ": 20,
    "512690.SH": 21,
    "515230.SH": 30,
    "159998.SZ": 31,
    "512980.SH": 32,
    "512880.SH": 40,
    "512200.SH": 41,
    "159996.SZ": 50,
    "515180.SH": 60,
    "512890.SH": 61,
    "159930.SZ": 70,
    "159697.SZ": 71,
    "515220.SH": 72,
    "159870.SZ": 73,
    "931994.CSI": 80,
    "515790.SH": 81,
    "512480.SH": 82,
    "TMT-COMM": 90,
}


BUCKET_ORDER = {
    "科技成长与高端制造": 10,
    "大消费与医药": 20,
    "周期资源": 30,
    "红利金融地产": 40,
}


def _topic_page_codes() -> dict[str, set[str]]:
    return {page["output"]: set(page["codes"]) for page in TOPIC_PAGES}


def _page_candidates_by_code() -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for page in TOPIC_PAGES:
        href = f"pages/{page['output']}"
        for code in page["codes"]:
            candidates.setdefault(code, []).append(href)
    return candidates


def _load_correlation_rows(theme_code: str) -> list[dict[str, str]]:
    csv_path = CORRELATION_DIR / f"theme_{theme_code.split('.')[0]}_to_sw_l2_correlation.csv"
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _fmt_corr(value: str | None) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "-"


def _derive_map(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "相关性结果缺失"

    top_names = [row["sw_name"] for row in rows[:3] if row.get("sw_name")]
    if not top_names:
        return "相关性结果缺失"
    if len(top_names) == 1:
        return top_names[0]
    return f"{top_names[0]}；关注 {', '.join(top_names[1:])}"


def _derive_note(rows: list[dict[str, str]], preferred_href: str, resolved_href: str) -> str:
    if not rows:
        return "相关性 CSV 缺失，需先重跑 daily update。"

    top = rows[0]
    note = (
        f"Top1 {top.get('sw_name', '-')}"
        f"（相关性 {_fmt_corr(top.get('corr_daily_ret'))}，龙头 {top.get('leader_top1_name') or '-'}）"
    )
    if len(rows) > 1:
        follow_names = [row["sw_name"] for row in rows[1:3] if row.get("sw_name")]
        if follow_names:
            note += f"；次级关注 {', '.join(follow_names)}"
    if resolved_href != preferred_href:
        note += "；首页链接已切换到覆盖当前 top1 行业的专题页"
    return note + "。"


def _derive_status(top: dict[str, str]) -> str:
    parts = [part for part in [top.get("final_label", "").strip(), top.get("crowding_label", "").strip()] if part]
    if parts:
        return " / ".join(parts)
    return "未纳入主扫描池 / 未计算"


def _resolve_href(preferred_href: str, rows: list[dict[str, str]], page_codes: dict[str, set[str]], page_candidates: dict[str, list[str]]) -> str:
    if not rows:
        return preferred_href

    top_sw_code = rows[0].get("sw_code", "")
    if not top_sw_code:
        return preferred_href

    if top_sw_code in page_codes.get(Path(preferred_href).name, set()):
        return preferred_href

    candidates = page_candidates.get(top_sw_code, [])
    return candidates[0] if candidates else preferred_href


def _card_with_live_data(card: dict[str, str], page_codes: dict[str, set[str]], page_candidates: dict[str, list[str]]) -> dict[str, str]:
    if "." not in card["code"]:
        return card.copy()

    rows = _load_correlation_rows(card["code"])
    resolved_href = _resolve_href(card["href"], rows, page_codes, page_candidates)
    live = card.copy()
    if rows:
        top = rows[0]
        live["status"] = _derive_status(top)
        live["map"] = _derive_map(rows)
        live["note"] = _derive_note(rows, card["href"], resolved_href)
    else:
        live["status"] = "相关性缺失"
        live["map"] = "相关性结果缺失"
        live["note"] = "未找到对应相关性 CSV，请检查 daily update 是否完整执行。"
    live["href"] = resolved_href
    return live


def _live_cards() -> list[dict[str, str]]:
    page_codes = _topic_page_codes()
    page_candidates = _page_candidates_by_code()
    return [_card_with_live_data(card, page_codes, page_candidates) for card in BASE_CARDS]


def _overview_table(cards: list[dict[str, str]]) -> str:
    rows = []
    sorted_cards = sorted(
        cards,
        key=lambda card: (
            BUCKET_ORDER.get(card["bucket"], 999),
            DISPLAY_ORDER.get(card["code"], 999),
            card["code"],
        ),
    )
    for card in sorted_cards:
        rows.append(
            f"""
<tr>
  <td><a class="target-link" href="{escape(card['href'])}">{escape(card['name'])}</a></td>
  <td class="mono">{escape(card['code'])}</td>
  <td><span class="status-pill">{escape(card['status'])}</span></td>
  <td>{escape(card['map'])}</td>
  <td><span class="table-bucket">{escape(card['bucket'])}</span></td>
  <td>{escape(card['note'])}</td>
</tr>
"""
        )

    return f"""
<section class="overview-table-section">
  <div class="section-title">
    <h1>观察标的一览表</h1>
    <p>首页状态、相关行业映射和备注直接读取最新相关性结果，避免静态文案与专题页脱节。</p>
  </div>
  <div class="table-wrap">
    <table class="overview-table">
      <thead>
        <tr>
          <th>标的</th>
          <th>代码</th>
          <th>策略状态</th>
          <th>申万二级映射</th>
          <th>分类</th>
          <th>观察要点</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def build_dashboard() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cards = _live_cards()
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF 标的观察总览</title>
  <style>
    :root {{
      --bg: #f3ead9;
      --paper: #fffaf1;
      --ink: #17262d;
      --muted: #66727a;
      --accent: #b64b2c;
      --accent-2: #1f6f78;
      --line: rgba(70, 52, 27, 0.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 8%, rgba(182, 75, 44, 0.18), transparent 30rem),
        radial-gradient(circle at 86% 12%, rgba(31, 111, 120, 0.15), transparent 26rem),
        linear-gradient(135deg, #fbf5ea 0%, var(--bg) 52%, #e5d2b4 100%);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 42px 20px 60px; }}
    header {{ margin-bottom: 28px; }}
    header h1 {{ margin: 0 0 10px; font-size: clamp(30px, 4vw, 52px); letter-spacing: -0.05em; }}
    header p {{ margin: 0; color: var(--muted); line-height: 1.8; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    .nav a {{
      color: var(--accent-2);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(255, 250, 241, 0.72);
    }}
    .overview-table-section {{
      margin-top: 26px;
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: rgba(255, 250, 241, 0.88);
      box-shadow: 0 18px 42px rgba(77, 54, 22, 0.10);
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      margin-bottom: 14px;
    }}
    .section-title h1 {{ margin: 0; font-size: 24px; }}
    .section-title p {{ margin: 0; color: var(--muted); line-height: 1.6; max-width: 620px; }}
    .table-wrap {{ overflow-x: auto; border-radius: 16px; border: 1px solid rgba(70, 52, 27, 0.10); }}
    .overview-table {{
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.44);
      font-size: 13px;
    }}
    .overview-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      text-align: left;
      padding: 12px 12px;
      color: #415056;
      background: #f0e2c8;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }}
    .overview-table td {{
      padding: 12px;
      vertical-align: top;
      border-bottom: 1px solid rgba(70, 52, 27, 0.10);
      line-height: 1.55;
    }}
    .overview-table tbody tr:hover {{ background: rgba(31, 111, 120, 0.06); }}
    .table-bucket {{
      display: inline-flex;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(31, 111, 120, 0.12);
      color: var(--accent-2);
      white-space: nowrap;
    }}
    .target-link {{ color: var(--ink); font-weight: 900; text-decoration: none; }}
    .target-link:hover {{ color: var(--accent); }}
    .status-pill {{
      display: inline-flex;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(182, 75, 44, 0.11);
      color: var(--accent);
      white-space: nowrap;
    }}
    .mono {{ font-family: Consolas, "Liberation Mono", monospace; font-weight: 700; color: var(--accent-2); }}
    .support {{ margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); line-height: 1.7; }}
    .support p {{ margin: 12px 0 0; }}
    @media (max-width: 860px) {{
      .section-title {{ display: block; }}
      .section-title p {{ margin-top: 8px; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>ETF 标的观察总览</h1>
    <p>首页按实际观察标的组织，状态和映射直接读取最新相关性结果。生成时间：{escape(generated_at)}</p>
  </header>
  {_overview_table(cards)}
  <footer class="support">
    <div class="nav">
      <a href="theme_watch_sop.md">SOP</a>
      <a href="daily_update_runbook.md">每日更新手册</a>
      <a href="theme_to_sw_watchlist.md">映射清单</a>
    </div>
    <p>以上内容仅用于个人研究、数据观察和策略复盘，不构成任何投资建议、买卖依据或收益承诺。</p>
  </footer>
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_dashboard()
