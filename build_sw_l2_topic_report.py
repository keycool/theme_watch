from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from build_sw_l2_visual_report import HISTORY_CSV, SCAN_CSV, _card


ROOT = Path(__file__).resolve().parent
CLASSIFY_CSV = ROOT / ".cache_scan_v2" / "sw_index_classify.csv"
DEFAULT_CODES = ["801125.SI", "801194.SI", "801193.SI"]
DEFAULT_OUTPUT = ROOT / "sw_l2_baijiu_insurance_brokerage_report.html"


def _fallback_row(code: str, history: pd.DataFrame, classify: pd.DataFrame, latest_date: str) -> pd.Series:
    classify_hit = classify[classify["index_code"].astype(str) == code]
    if classify_hit.empty:
        industry_name = code
    else:
        industry_name = str(classify_hit.iloc[0].get("industry_name", code))

    latest = history.sort_values("trade_date").iloc[-1]
    total_mv = pd.to_numeric(latest.get("total_mv"), errors="coerce")
    total_mv_yi = None if pd.isna(total_mv) else float(total_mv) / 10000.0

    return pd.Series(
        {
            "industry_code": code,
            "industry_name": industry_name,
            "latest_date": latest_date,
            "total_mv_yi": total_mv_yi,
            "final_label": "未纳入主扫描池",
            "crowding_label": "未计算",
            "leader_top1_name": "-",
            "leader_top1_pct_change": None,
            "absorption_rate_rank_pct": None,
            "summary_line": "该行业有申万历史行情，但未进入当前主扫描输出；此卡仅用于主题关联观察。",
        }
    )


def build_topic_report(codes: list[str], title: str, output_path: Path) -> None:
    scan = pd.read_csv(SCAN_CSV)
    classify = pd.read_csv(CLASSIFY_CSV, dtype=str)
    history = pd.read_csv(HISTORY_CSV, dtype={"ts_code": str, "trade_date": str})
    history = history.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    code_order = {code: index for index, code in enumerate(codes)}
    history_map = {code: group.copy() for code, group in history.groupby("ts_code")}
    scan_map = {str(row["industry_code"]): row for _, row in scan.iterrows()}

    cards: list[str] = []
    missing: list[str] = []
    latest_date = str(scan["latest_date"].dropna().max())
    for code in codes:
        industry_history = history_map.get(code)
        if industry_history is None or industry_history.empty:
            missing.append(code)
            continue

        if code in scan_map:
            row = scan_map[code]
        else:
            row = _fallback_row(code, industry_history, classify, latest_date)
        cards.append(_card(row, industry_history))

    latest_date = escape(latest_date)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    missing_note = ""
    if missing:
        missing_note = f"<p class=\"warn\">未找到数据：{escape(', '.join(missing))}</p>"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --paper: #f7efe1;
      --ink: #1b2a2f;
      --muted: #66747a;
      --line: #dac7a8;
      --accent: #bb4d2d;
      --accent-2: #1f6f78;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 8%, rgba(187, 77, 45, 0.18), transparent 28rem),
        radial-gradient(circle at 88% 18%, rgba(31, 111, 120, 0.16), transparent 24rem),
        linear-gradient(135deg, #fbf6ed 0%, var(--paper) 52%, #ead9bd 100%);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 40px 20px 56px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(28px, 4vw, 46px); letter-spacing: -0.04em; }}
    header p {{ margin: 0; color: var(--muted); line-height: 1.7; }}
    .warn {{ margin-top: 12px; color: #9f3e25; }}
    .grid-cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }}
    .card {{
      border: 1px solid rgba(69, 52, 28, 0.16);
      background: rgba(255, 250, 241, 0.88);
      box-shadow: 0 18px 42px rgba(77, 54, 22, 0.10);
      backdrop-filter: blur(8px);
      border-radius: 22px;
      padding: 18px;
      overflow: hidden;
    }}
    .card-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
    .card h2 {{ margin: 0 0 4px; font-size: 22px; }}
    .card p {{ margin: 0; color: var(--muted); }}
    .badges {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }}
    .badge {{ border-radius: 999px; padding: 7px 10px; font-size: 12px; white-space: nowrap; }}
    .badge.label {{ background: rgba(31, 111, 120, 0.14); color: var(--accent-2); }}
    .badge.crowding {{ background: rgba(187, 77, 45, 0.13); color: var(--accent); }}
    .sparkline {{ width: 100%; margin: 16px 0 6px; display: block; }}
    .grid {{ stroke: var(--line); stroke-width: 1; stroke-dasharray: 4 8; }}
    .line {{ fill: none; stroke-linejoin: round; stroke-linecap: round; stroke-width: 3.2; }}
    .line.close {{ stroke: var(--accent); }}
    .line.ma {{ stroke: var(--accent-2); opacity: 0.72; }}
    .amount-bars rect {{ fill: rgba(31, 111, 120, 0.14); }}
    .axis-text {{ fill: var(--muted); font-size: 12px; }}
    .axis-text.right {{ text-anchor: end; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 10px 16px; font-size: 13px; color: var(--muted); }}
    .metrics strong {{ color: var(--ink); }}
    .summary {{ margin-top: 12px !important; line-height: 1.6; font-size: 13px; }}
    .empty-chart {{ padding: 80px 0; text-align: center; color: var(--muted); }}
    @media (max-width: 1080px) {{ .grid-cards {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{escape(title)}</h1>
    <p>数据主线：Tushare 申万二级行业 · 最新扫描日：{latest_date} · 生成时间：{escape(generated_at)}</p>
    <p>红线为收盘价，蓝线为 MA250，底部浅蓝柱为成交额；卡片内已加入“连续低于 MA250”统计。</p>
    {missing_note}
  </header>
  <section class="grid-cards">
    {''.join(cards)}
  </section>
</main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    print(f"wrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", default=DEFAULT_CODES)
    parser.add_argument("--title", default="白酒、保险和证券专题图形报告")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    build_topic_report(args.codes, args.title, Path(args.output))


if __name__ == "__main__":
    main()
