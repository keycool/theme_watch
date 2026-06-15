from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"
HISTORY_CSV = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
OUTPUT_HTML = ROOT / "sw_l2_strategy_visual_report.html"

WATCH_LABELS = {"启动确认", "接近启动", "观察中"}
TREND_LABELS = {"趋势延续型偏强", "趋势延续型强势"}
HOT_LABELS = {"过热预警", "过热退潮"}


def _fmt_num(value: object, digits: int = 2, default: str = "-") -> str:
    if value is None or pd.isna(value):
        return default
    return f"{float(value):,.{digits}f}"


def _fmt_pct(value: object, digits: int = 2, default: str = "-") -> str:
    if value is None or pd.isna(value):
        return default
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_sigma(value: object, digits: int = 2, default: str = "-") -> str:
    if value is None or pd.isna(value):
        return default
    return f"{float(value):.{digits}f}σ"


def _priority(row: pd.Series) -> tuple[int, float]:
    label = str(row.get("final_label", ""))
    crowding = str(row.get("crowding_label", ""))
    if label == "启动确认":
        rank = 0
    elif label == "接近启动":
        rank = 1
    elif label == "观察中":
        rank = 2
    elif crowding in HOT_LABELS:
        rank = 3
    elif label in TREND_LABELS:
        rank = 4
    else:
        rank = 5
    return rank, -float(row.get("total_mv_yi", 0) or 0)


def _polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _line_points(values: pd.Series, min_value: float, max_value: float, width: int, top: int, height: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    span = max(max_value - min_value, 1e-9)
    values = values.reset_index(drop=True)
    denominator = max(len(values) - 1, 1)
    for index, value in values.items():
        if pd.isna(value):
            continue
        x = index / denominator * width
        y = top + (max_value - float(value)) / span * height
        points.append((x, y))
    return points


def _build_svg(history: pd.DataFrame) -> str:
    full_history = history.copy()
    full_history["close"] = pd.to_numeric(full_history["close"], errors="coerce")
    full_history["amount"] = pd.to_numeric(full_history["amount"], errors="coerce")
    full_history["ma250"] = full_history["close"].rolling(250).mean()
    chart = full_history.tail(260).copy()

    plot_values = pd.concat([chart["close"], chart["ma250"]]).dropna()
    if plot_values.empty:
        return '<div class="empty-chart">历史数据不足，暂无法画图</div>'

    width = 620
    top = 18
    price_height = 190
    amount_top = 226
    amount_height = 42
    min_value = float(plot_values.min())
    max_value = float(plot_values.max())
    padding = (max_value - min_value) * 0.08 or 1
    min_value -= padding
    max_value += padding

    close_points = _line_points(chart["close"], min_value, max_value, width, top, price_height)
    ma_points = _line_points(chart["ma250"], min_value, max_value, width, top, price_height)

    amount_max = float(chart["amount"].max()) if chart["amount"].notna().any() else 0
    bar_count = len(chart)
    bar_width = max(width / max(bar_count, 1), 1.0)
    bars: list[str] = []
    if amount_max > 0:
        for index, value in chart["amount"].reset_index(drop=True).items():
            if pd.isna(value):
                continue
            height = float(value) / amount_max * amount_height
            x = index / max(bar_count - 1, 1) * width
            y = amount_top + amount_height - height
            bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{height:.1f}" />')

    latest = chart.iloc[-1]
    close_text = _fmt_num(latest.get("close"))
    ma_text = _fmt_num(latest.get("ma250"))
    start_date = str(chart.iloc[0]["trade_date"])
    end_date = str(chart.iloc[-1]["trade_date"])

    return f"""
<svg class="sparkline" viewBox="0 0 660 300" role="img" aria-label="close and ma250 chart">
  <line class="grid" x1="0" y1="{top}" x2="{width}" y2="{top}" />
  <line class="grid" x1="0" y1="{top + price_height / 2}" x2="{width}" y2="{top + price_height / 2}" />
  <line class="grid" x1="0" y1="{top + price_height}" x2="{width}" y2="{top + price_height}" />
  <g class="amount-bars">{''.join(bars)}</g>
  <polyline class="line ma" points="{_polyline(ma_points)}" />
  <polyline class="line close" points="{_polyline(close_points)}" />
  <text class="axis-text" x="0" y="292">{escape(start_date)}</text>
  <text class="axis-text right" x="{width}" y="292">{escape(end_date)}</text>
  <text class="axis-text right" x="650" y="36">收盘 {close_text}</text>
  <text class="axis-text right" x="650" y="56">MA250 {ma_text}</text>
</svg>
"""


def _below_ma250_streak(history: pd.DataFrame) -> int | None:
    full_history = history.copy()
    full_history["close"] = pd.to_numeric(full_history["close"], errors="coerce")
    full_history["ma250"] = full_history["close"].rolling(250).mean()

    valid = full_history.dropna(subset=["close", "ma250"])
    if valid.empty:
        return None

    streak = 0
    for _, row in valid.iloc[::-1].iterrows():
        if float(row["close"]) < float(row["ma250"]):
            streak += 1
            continue
        break
    return streak


def _ma250_convergence(history: pd.DataFrame) -> dict[str, object]:
    full_history = history.copy()
    full_history["close"] = pd.to_numeric(full_history["close"], errors="coerce")
    full_history["ma250"] = full_history["close"].rolling(250).mean()
    full_history["ma250_gap"] = full_history["close"] / full_history["ma250"] - 1

    valid = full_history.dropna(subset=["close", "ma250", "ma250_gap"])
    if valid.empty:
        return {
            "below_streak": None,
            "latest_gap": None,
            "min_gap_120": None,
            "repair_from_120_low": None,
            "repair_sigma": None,
            "stage": "数据不足",
        }

    latest = valid.iloc[-1]
    below_streak = 0
    for _, row in valid.iloc[::-1].iterrows():
        if float(row["ma250_gap"]) < 0:
            below_streak += 1
            continue
        break

    last_120 = valid.tail(120)
    latest_gap = float(latest["ma250_gap"])
    min_gap_120 = float(last_120["ma250_gap"].min())
    repair_from_120_low = latest_gap - min_gap_120
    gap_std_120 = float(last_120["ma250_gap"].std())
    repair_sigma = None if pd.isna(gap_std_120) or gap_std_120 <= 0 else repair_from_120_low / gap_std_120

    if latest_gap >= 0:
        stage = "已越过年线"
    elif latest_gap >= -0.03:
        stage = "贴近年线"
    elif repair_from_120_low >= 0.05:
        stage = "远离后修复"
    elif below_streak >= 60:
        stage = "长期年线下方"
    else:
        stage = "年线下方"

    return {
        "below_streak": below_streak,
        "latest_gap": latest_gap,
        "min_gap_120": min_gap_120,
        "repair_from_120_low": repair_from_120_low,
        "repair_sigma": repair_sigma,
        "stage": stage,
    }


def _card(row: pd.Series, history: pd.DataFrame) -> str:
    label = escape(str(row.get("final_label", "-")))
    crowding = escape(str(row.get("crowding_label", "-")))
    industry_name = escape(str(row.get("industry_name", "-")))
    industry_code = escape(str(row.get("industry_code", "-")))
    leader = escape(str(row.get("leader_top1_name", "-")))
    leader_pct = _fmt_pct(float(row["leader_top1_pct_change"]) / 100 if pd.notna(row.get("leader_top1_pct_change")) else None)
    mv = _fmt_num(row.get("total_mv_yi"), 0)
    absorption_rank = _fmt_pct(row.get("absorption_rate_rank_pct"))
    ma250_convergence = _ma250_convergence(history)
    below_ma250_streak = ma250_convergence["below_streak"]
    below_ma250_text = "-" if below_ma250_streak is None else f"{below_ma250_streak} 天"
    latest_gap_text = _fmt_pct(ma250_convergence["latest_gap"])
    repair_text = _fmt_sigma(ma250_convergence["repair_sigma"])
    summary = escape(str(row.get("summary_line", "")))

    return f"""
<article class="card">
  <div class="card-head">
    <div>
      <h2>{industry_name}</h2>
      <p>{industry_code} · 总市值约 {mv} 亿</p>
    </div>
    <div class="badges">
      <span class="badge label">{label}</span>
      <span class="badge crowding">{crowding}</span>
    </div>
  </div>
  {_build_svg(history)}
  <div class="metrics">
    <span>龙头：<strong>{leader}</strong></span>
    <span>龙头当日涨幅：<strong>{leader_pct}</strong></span>
    <span>连续低于 MA250：<strong>{below_ma250_text}</strong></span>
    <span>当前距 MA250：<strong>{latest_gap_text}</strong></span>
    <span>偏离修复σ：<strong>{repair_text}</strong></span>
    <span>吸筹率分位：<strong>{absorption_rank}</strong></span>
  </div>
  <p class="summary">{summary}</p>
</article>
"""


def _overview(scan: pd.DataFrame) -> str:
    final_counts = scan["final_label"].value_counts().to_dict()
    crowding_counts = scan["crowding_label"].value_counts().to_dict()

    def pills(items: dict[str, int]) -> str:
        return "".join(
            f'<span class="pill"><b>{escape(str(key))}</b>{int(value)}</span>'
            for key, value in sorted(items.items(), key=lambda item: (-item[1], str(item[0])))
        )

    return f"""
<section class="overview">
  <div>
    <h2>策略状态</h2>
    <div class="pill-row">{pills(final_counts)}</div>
  </div>
  <div>
    <h2>拥挤度辅助标签</h2>
    <div class="pill-row">{pills(crowding_counts)}</div>
  </div>
</section>
"""


def build_report() -> None:
    scan = pd.read_csv(SCAN_CSV)
    history = pd.read_csv(HISTORY_CSV, dtype={"ts_code": str, "trade_date": str})
    history = history.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    scan = scan.copy()
    scan["_priority"] = scan.apply(_priority, axis=1)
    selected = scan[
        scan["final_label"].isin(WATCH_LABELS)
        | scan["final_label"].isin(TREND_LABELS)
        | scan["crowding_label"].isin(HOT_LABELS)
    ].sort_values("_priority").head(18)

    history_map = {code: group.copy() for code, group in history.groupby("ts_code")}
    cards = []
    for _, row in selected.iterrows():
        code = str(row["industry_code"])
        industry_history = history_map.get(code)
        if industry_history is None or industry_history.empty:
            continue
        cards.append(_card(row, industry_history))

    latest_date = escape(str(scan["latest_date"].dropna().max()))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>申万二级行业启动策略图形报告</title>
  <style>
    :root {{
      --paper: #f6efe3;
      --ink: #1d2930;
      --muted: #65717a;
      --line: #d8c7ac;
      --accent: #bb4d2d;
      --accent-2: #1f6f78;
      --card: #fffaf1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 15% 10%, rgba(187, 77, 45, 0.18), transparent 28rem),
        linear-gradient(135deg, #fbf5ea 0%, var(--paper) 48%, #eadac1 100%);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 40px 20px 56px; }}
    header {{ margin-bottom: 26px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(28px, 4vw, 48px); letter-spacing: -0.04em; }}
    header p {{ margin: 0; color: var(--muted); line-height: 1.7; }}
    .overview {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin: 26px 0;
    }}
    .overview > div, .card {{
      border: 1px solid rgba(69, 52, 28, 0.16);
      background: rgba(255, 250, 241, 0.86);
      box-shadow: 0 18px 42px rgba(77, 54, 22, 0.10);
      backdrop-filter: blur(8px);
      border-radius: 22px;
    }}
    .overview > div {{ padding: 18px; }}
    .overview h2 {{ margin: 0 0 12px; font-size: 17px; }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .pill {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      border-radius: 999px;
      padding: 8px 12px;
      background: #efe0c7;
      color: #4f3b1f;
      font-size: 13px;
    }}
    .pill b {{ color: var(--ink); }}
    .grid-cards {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .card {{ padding: 18px; overflow: hidden; }}
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
    footer {{ margin-top: 26px; color: var(--muted); font-size: 13px; line-height: 1.7; }}
    @media (max-width: 860px) {{
      .overview, .grid-cards {{ grid-template-columns: 1fr; }}
      .card-head {{ display: block; }}
      .badges {{ justify-content: flex-start; margin-top: 10px; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>申万二级行业启动策略图形报告</h1>
    <p>数据主线：Tushare · 最新扫描日：{latest_date} · 生成时间：{escape(generated_at)}</p>
    <p>图中红线为收盘价，蓝线为 MA250，底部浅蓝柱为成交额强弱。这个页面用于快速肉眼校验“低位收敛、年线位置、是否已过热”。</p>
  </header>
  {_overview(scan)}
  <section class="grid-cards">
    {''.join(cards)}
  </section>
  <footer>
    <p>说明：本报告只做展示，不改变策略判定；候选来自 `sw_l2_strategy_scan.csv`，历史行情来自 `.cache_scan_v2/sw_daily_full_history.csv`。</p>
  </footer>
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_report()
