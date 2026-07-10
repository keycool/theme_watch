from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"
HISTORY_CSV = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
OUTPUT_HTML = ROOT / "sw_l2_strategy_visual_report.html"

WATCH_LABELS = {"启动确认", "接近启动", "早期启动", "观察中"}
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


def _fmt_ratio(numerator: object, denominator: object) -> str:
    if denominator is None or pd.isna(denominator) or int(float(denominator)) <= 0:
        return "-"
    if numerator is None or pd.isna(numerator):
        return "-"
    return f"{int(float(numerator))}/{int(float(denominator))}"


def _display_signal(value: object) -> str:
    if value is None or pd.isna(value):
        return "未触发"
    text = str(value).strip()
    return text or "未触发"


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


def _line_points(
    values: pd.Series,
    min_value: float,
    max_value: float,
    width: int,
    top: int,
    height: int,
) -> list[tuple[float, float]]:
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


def _line_hint(label: str, available_points: int, required_points: int) -> str:
    if available_points > 0:
        return f"{label} 已绘制"
    return f"{label} 样本不足（至少 {required_points} 个交易日）"


def _build_svg(history: pd.DataFrame) -> str:
    full_history = history.copy()
    full_history["close"] = pd.to_numeric(full_history["close"], errors="coerce")
    full_history["amount"] = pd.to_numeric(full_history["amount"], errors="coerce")
    full_history["ma60"] = full_history["close"].rolling(60).mean()
    full_history["ma250"] = full_history["close"].rolling(250).mean()
    chart = full_history.tail(260).copy()

    plot_values = pd.concat([chart["close"], chart["ma60"], chart["ma250"]]).dropna()
    if plot_values.empty:
        return '<div class="empty-chart">历史数据不足，暂时无法绘图</div>'

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
    ma60_points = _line_points(chart["ma60"], min_value, max_value, width, top, price_height)
    ma250_points = _line_points(chart["ma250"], min_value, max_value, width, top, price_height)

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
    ma60_text = _fmt_num(latest.get("ma60"), default="样本不足")
    ma250_text = _fmt_num(latest.get("ma250"), default="样本不足")
    start_date = str(chart.iloc[0]["trade_date"])
    end_date = str(chart.iloc[-1]["trade_date"])
    ma_hint = f"{_line_hint('MA60', len(ma60_points), 60)}；{_line_hint('MA250', len(ma250_points), 250)}"

    return f"""
<svg class="sparkline" viewBox="0 0 660 320" role="img" aria-label="close ma60 and ma250 chart">
  <line class="grid" x1="0" y1="{top}" x2="{width}" y2="{top}" />
  <line class="grid" x1="0" y1="{top + price_height / 2}" x2="{width}" y2="{top + price_height / 2}" />
  <line class="grid" x1="0" y1="{top + price_height}" x2="{width}" y2="{top + price_height}" />
  <g class="amount-bars">{''.join(bars)}</g>
  <polyline class="line ma" points="{_polyline(ma250_points)}" />
  <polyline class="line ma60" points="{_polyline(ma60_points)}" />
  <polyline class="line close" points="{_polyline(close_points)}" />
  <text class="axis-text" x="0" y="292">{escape(start_date)}</text>
  <text class="axis-text right" x="{width}" y="292">{escape(end_date)}</text>
  <text class="axis-text right" x="650" y="36">收盘 {close_text}</text>
  <text class="axis-text right" x="650" y="56">MA60 {ma60_text}</text>
  <text class="axis-text right" x="650" y="76">MA250 {ma250_text}</text>
  <text class="axis-text" x="0" y="312">{escape(ma_hint)}</text>
</svg>
"""


def _ma250_convergence(history: pd.DataFrame) -> dict[str, object]:
    full_history = history.copy()
    full_history["close"] = pd.to_numeric(full_history["close"], errors="coerce")
    full_history["ma250"] = full_history["close"].rolling(250).mean()
    full_history["ma250_gap"] = full_history["close"] / full_history["ma250"] - 1

    valid = full_history.dropna(subset=["close", "ma250", "ma250_gap"])
    if valid.empty:
        return {
            "below_streak": None,
            "gap_sigma": None,
        }

    below_streak = 0
    for _, row in valid.iloc[::-1].iterrows():
        if float(row["ma250_gap"]) < 0:
            below_streak += 1
            continue
        break

    last_120 = valid.tail(120)
    latest_gap = float(valid.iloc[-1]["ma250_gap"])
    gap_mean_120 = float(last_120["ma250_gap"].mean())
    gap_std_120 = float(last_120["ma250_gap"].std())
    gap_sigma = None if pd.isna(gap_std_120) or gap_std_120 <= 0 else (latest_gap - gap_mean_120) / gap_std_120
    return {
        "below_streak": below_streak,
        "gap_sigma": gap_sigma,
    }


def _spot_volatility(history: pd.DataFrame) -> dict[str, object]:
    full_history = history.copy()
    for column in ["high", "low", "close"]:
        full_history[column] = pd.to_numeric(full_history[column], errors="coerce")
    full_history["spot_volatility"] = (full_history["high"] - full_history["low"]) / full_history["close"]

    valid = full_history.dropna(subset=["spot_volatility"])
    if valid.empty:
        return {"vol_sigma": None}

    last_120 = valid.tail(120)
    latest_vol = float(valid.iloc[-1]["spot_volatility"])
    vol_mean_120 = float(last_120["spot_volatility"].mean())
    vol_std_120 = float(last_120["spot_volatility"].std())
    return {
        "vol_sigma": None if pd.isna(vol_std_120) or vol_std_120 <= 0 else (latest_vol - vol_mean_120) / vol_std_120,
    }


def _card(row: pd.Series, history: pd.DataFrame) -> str:
    label = escape(str(row.get("final_label", "-")))
    crowding = escape(str(row.get("crowding_label", "-")))
    industry_name = escape(str(row.get("industry_name", "-")))
    industry_code = escape(str(row.get("industry_code", "-")))
    leader_count = row.get("leader_count")
    leader_active_count = row.get("leader_active_count")
    leaders_above_ma60_count = row.get("leaders_above_ma60_count")
    leaders_above_ma250_count = row.get("leaders_above_ma250_count")
    leader_group_detail = escape(str(row.get("leader_group_detail", "") or row.get("leader_group_names", "") or "-"))
    mv = _fmt_num(row.get("total_mv_yi"), 0)
    absorption_rank = _fmt_pct(row.get("absorption_rate_rank_pct"))
    ma60_signal = escape(_display_signal(row.get("ma60_early_signal")))
    ma250_convergence = _ma250_convergence(history)
    below_ma250_streak = ma250_convergence["below_streak"]
    below_ma250_text = "样本不足" if below_ma250_streak is None else f"{below_ma250_streak} 天"
    gap_sigma_text = _fmt_sigma(ma250_convergence["gap_sigma"], default="样本不足")
    spot_volatility = _spot_volatility(history)
    vol_sigma_text = _fmt_sigma(spot_volatility["vol_sigma"], default="样本不足")
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
  <div class="metric-groups">
    <div class="metric-group primary">
      <h3>主指标</h3>
      <div class="metrics">
        <span>连续低于 MA250：<strong>{below_ma250_text}</strong></span>
        <span>偏离度σ：<strong>{gap_sigma_text}</strong></span>
        <span>MA60信号：<strong>{ma60_signal}</strong></span>
        <span>强势龙头：<strong>{_fmt_ratio(leader_active_count, leader_count)}</strong></span>
        <span>MA60：<strong>{_fmt_ratio(leaders_above_ma60_count, leader_count)}</strong></span>
        <span>MA250：<strong>{_fmt_ratio(leaders_above_ma250_count, leader_count)}</strong></span>
      </div>
    </div>
    <div class="metric-group auxiliary">
      <h3>辅助指标</h3>
      <div class="metrics">
        <span>吸筹率分位：<strong>{absorption_rank}</strong></span>
        <span>波动率σ：<strong>{vol_sigma_text}</strong></span>
      </div>
    </div>
  </div>
  <details class="leader-details">
    <summary>查看龙头群涨跌幅</summary>
    <p>{leader_group_detail}</p>
  </details>
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
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 8%, rgba(187, 77, 45, 0.22), transparent 30rem),
        radial-gradient(circle at 88% 16%, rgba(31, 111, 120, 0.18), transparent 24rem),
        linear-gradient(135deg, #fbf6ed 0%, var(--paper) 50%, #e9d8bf 100%);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 32px 20px 48px; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(32px, 4vw, 48px); letter-spacing: -0.04em; }}
    header p {{ margin: 0; color: var(--muted); line-height: 1.7; }}
    .overview {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 22px 0 24px; }}
    .overview > div {{
      border-radius: 20px;
      padding: 18px 20px;
      background: rgba(255, 250, 241, 0.78);
      border: 1px solid rgba(69, 52, 28, 0.12);
      box-shadow: 0 14px 32px rgba(77, 54, 22, 0.08);
    }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{ border-radius: 999px; padding: 6px 10px; background: rgba(31, 111, 120, 0.1); color: var(--accent-2); }}
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
    .line.ma60 {{ stroke: #d59a21; opacity: 0.76; stroke-width: 2.6; }}
    .line.ma {{ stroke: var(--accent-2); opacity: 0.72; }}
    .amount-bars rect {{ fill: rgba(31, 111, 120, 0.14); }}
    .axis-text {{ fill: var(--muted); font-size: 12px; }}
    .axis-text.right {{ text-anchor: end; }}
    .metric-groups {{ display: grid; grid-template-columns: 1.45fr 1fr; gap: 10px; margin-top: 8px; }}
    .metric-group {{ border-radius: 16px; padding: 10px 12px; border: 1px solid rgba(69, 52, 28, 0.10); }}
    .metric-group.primary {{ background: rgba(31, 111, 120, 0.07); }}
    .metric-group.auxiliary {{ background: rgba(187, 77, 45, 0.06); }}
    .metric-group h3 {{ margin: 0 0 8px; font-size: 13px; letter-spacing: 0.08em; color: var(--muted); }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 10px 16px; font-size: 13px; color: var(--muted); }}
    .metrics strong {{ color: var(--ink); }}
    .leader-details {{ margin-top: 10px; border-radius: 14px; background: rgba(69, 52, 28, 0.05); padding: 9px 12px; }}
    .leader-details summary {{ cursor: pointer; color: var(--muted); font-size: 12px; }}
    .leader-details p {{ margin-top: 8px !important; font-size: 12px; line-height: 1.7; color: var(--muted); }}
    .summary {{ margin-top: 12px !important; line-height: 1.6; font-size: 13px; }}
    .empty-chart {{ padding: 80px 0; text-align: center; color: var(--muted); }}
    @media (max-width: 1080px) {{
      .overview, .grid-cards, .metric-groups {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>申万二级行业启动策略图形报告</h1>
    <p>数据主线：Tushare 申万二级行业 · 最新扫描日：{latest_date} · 生成时间：{escape(generated_at)}</p>
    <p>图中红线为收盘价，琥珀线为 MA60，蓝线为 MA250，底部浅蓝柱为成交额强弱。“强势龙头”指龙头群中当日涨幅达到 5% 或近 5 日涨幅达到 5% 的数量。</p>
  </header>
  {_overview(scan)}
  <section class="grid-cards">
    {''.join(cards)}
  </section>
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_report()
