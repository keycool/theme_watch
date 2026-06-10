import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
SW_DAILY_PATH = ROOT / ".cache_scan_v2" / "sw_daily_20250506_20260630.csv"
SW_CLASSIFY_PATH = ROOT / ".cache_scan_v2" / "sw_index_classify.csv"
TDX_SNAPSHOT_PATH = ROOT / "tdx_white_liquor_snapshot_20260603.csv"
REPORT_PATH = ROOT / "hybrid_white_liquor_report.md"

SW_PROXY_CODE = "801120.SI"
SW_PROXY_NAME = "食品饮料"
TDX_BOARD_CODE = "881135"
TDX_BOARD_NAME = "白酒"


def load_sw_daily() -> pd.DataFrame:
    df = pd.read_csv(SW_DAILY_PATH)
    numeric_cols = ["open", "high", "low", "close", "amount"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def load_tdx_snapshot() -> pd.DataFrame:
    df = pd.read_csv(TDX_SNAPSHOT_PATH)
    numeric_cols = ["now_price", "pct_change", "vol", "amount", "turnover_pct", "latest_mv", "ma60", "ma250"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["above_ma60"] = df["now_price"] > df["ma60"]
    df["above_ma250"] = df["now_price"] > df["ma250"]
    return df.sort_values("latest_mv", ascending=False).reset_index(drop=True)


def build_histories(sw_daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    histories = {}
    for ts_code, group in sw_daily.groupby("ts_code"):
        df = group.sort_values("trade_date").reset_index(drop=True).copy()
        df["ma250"] = df["close"].rolling(250).mean()
        df["amount_ma20"] = df["amount"].rolling(20).mean()
        histories[ts_code] = df
    return histories


def return_rank_pct(histories: dict[str, pd.DataFrame]) -> dict[str, float]:
    scores = {}
    for code, df in histories.items():
        if len(df) < 121:
            continue
        scores[code] = df.iloc[-1]["close"] / df.iloc[-121]["close"] - 1
    return pd.Series(scores).rank(pct=True).to_dict()


def convergence_rule(df: pd.DataFrame, rank_pct: float) -> tuple[bool, float, float]:
    last_120 = df.tail(120)
    first_80 = last_120.head(80)
    last_40 = last_120.tail(40)
    first_range = (first_80["high"].max() - first_80["low"].min()) / first_80["close"].mean()
    last_range = (last_40["high"].max() - last_40["low"].min()) / last_40["close"].mean()
    no_new_low = last_40["low"].min() >= last_120["low"].min() * 1.02
    range_contracts = last_range <= first_range * 0.90
    lagging = rank_pct <= 0.5
    ret_120d = last_120.iloc[-1]["close"] / last_120.iloc[0]["close"] - 1
    return bool(no_new_low and range_contracts and lagging), float(ret_120d), float(last_range / first_range)


def breakout_rule(df: pd.DataFrame) -> tuple[bool, float, float]:
    latest = df.iloc[-1]
    price_ratio = latest["close"] / latest["ma250"] if pd.notna(latest["ma250"]) else math.nan
    amount_ratio = latest["amount"] / latest["amount_ma20"] if pd.notna(latest["amount_ma20"]) else math.nan
    ok = bool(price_ratio >= 1.03 and amount_ratio >= 1.20) if not math.isnan(price_ratio) and not math.isnan(amount_ratio) else False
    return ok, float(price_ratio), float(amount_ratio)


def summarize_proxy_board() -> dict[str, object]:
    sw_daily = load_sw_daily()
    histories = build_histories(sw_daily)
    ranks = return_rank_pct(histories)
    proxy = histories[SW_PROXY_CODE]
    latest = proxy.iloc[-1]
    enough_120d = len(proxy) >= 120
    enough_250d = len(proxy) >= 250
    if enough_120d:
        convergence_ok, ret_120d, range_ratio = convergence_rule(proxy, ranks.get(SW_PROXY_CODE, math.nan))
    else:
        convergence_ok, ret_120d, range_ratio = False, math.nan, math.nan
    if enough_250d:
        breakout_ok, price_ratio, amount_ratio = breakout_rule(proxy)
    else:
        breakout_ok, price_ratio, amount_ratio = False, math.nan, math.nan
    return {
        "latest_date": str(latest["trade_date"]),
        "sample_size": int(len(proxy)),
        "close": float(latest["close"]),
        "ma250": float(latest["ma250"]) if pd.notna(latest["ma250"]) else math.nan,
        "amount": float(latest["amount"]),
        "amount_ma20": float(latest["amount_ma20"]) if pd.notna(latest["amount_ma20"]) else math.nan,
        "ret_120d": float(ret_120d),
        "rank_pct": float(ranks.get(SW_PROXY_CODE, math.nan)),
        "convergence_ok": convergence_ok,
        "breakout_ok": breakout_ok,
        "price_ratio": price_ratio,
        "amount_ratio": amount_ratio,
        "range_ratio": range_ratio,
        "enough_120d": enough_120d,
        "enough_250d": enough_250d,
    }


def summarize_tdx_board() -> dict[str, object]:
    tdx = load_tdx_snapshot()
    leaders = tdx.head(5).copy()
    leaders["vs_ma60_pct"] = (leaders["now_price"] / leaders["ma60"] - 1) * 100
    leaders["vs_ma250_pct"] = (leaders["now_price"] / leaders["ma250"] - 1) * 100
    strongest = tdx.sort_values("pct_change", ascending=False).head(5).copy()
    return {
        "component_count": int(len(tdx)),
        "leaders": leaders,
        "above_ma60_count": int(tdx["above_ma60"].sum()),
        "above_ma250_count": int(tdx["above_ma250"].sum()),
        "strongest": strongest[["sec_name", "pct_change", "turnover_pct", "amount"]],
    }


def build_report() -> str:
    proxy = summarize_proxy_board()
    tdx = summarize_tdx_board()

    lines = [
        "# 白酒混合原型验证",
        "",
        "## 口径说明",
        f"- 板块历史趋势代理：申万一级 `{SW_PROXY_NAME}`（`{SW_PROXY_CODE}`）",
        f"- 成分股/龙头快照：通达信 `{TDX_BOARD_NAME}` 板块（`{TDX_BOARD_CODE}`）",
        "- 这是一个小规模混合原型，不是正式全行业模型。",
        "",
        "## 板块层判断",
        f"- 最新交易日：`{proxy['latest_date']}`",
        f"- 当前可用历史样本：`{proxy['sample_size']}` 个交易日",
        f"- 收盘价 / 250日均线：`{proxy['close']:.2f}` / `{proxy['ma250']:.2f}`",
        f"- 价格相对年线：`{proxy['price_ratio']:.3f}`",
        f"- 成交额 / 20日均额：`{proxy['amount']:.0f}` / `{proxy['amount_ma20']:.0f}`",
        f"- 量能相对20日均额：`{proxy['amount_ratio']:.3f}`",
        f"- 120日涨幅：`{proxy['ret_120d'] * 100:.2f}%`",
        f"- 120日涨幅分位：`{proxy['rank_pct']:.3f}`",
        f"- 收敛结构：`{'满足' if proxy['convergence_ok'] else '不满足'}`",
        f"- 收敛振幅比（后40日/前80日）：`{proxy['range_ratio']:.3f}`",
        f"- 放量过年线：`{'满足' if proxy['breakout_ok'] else '不满足'}`",
        "",
        "### 板块层备注",
        f"- `120日结构判断` 当前{'可用' if proxy['enough_120d'] else '不可用'}。",
        f"- `250日年线判断` 当前{'可用' if proxy['enough_250d'] else '不可用'}。",
        "- 当前 `.cache_scan_v2/sw_daily_20250506_20260630.csv` 实际只覆盖到 10 个交易日，因此板块层结论只能作为占位验证，不能视为正式判断。",
        "",
        "## 龙头层判断",
        f"- 白酒成分股样本数：`{tdx['component_count']}`",
        f"- 站上60日均线家数：`{tdx['above_ma60_count']}`",
        f"- 站上250日均线家数：`{tdx['above_ma250_count']}`",
        "",
        "### 市值前五龙头",
        "",
        "| 名称 | 最新价 | 涨跌幅 | 换手率 | 相对60日均线 | 相对250日均线 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for _, row in tdx["leaders"].iterrows():
        lines.append(
            f"| {row['sec_name']} | {row['now_price']:.2f} | {row['pct_change']:.2f}% | {row['turnover_pct']:.2f}% | {row['vs_ma60_pct']:.2f}% | {row['vs_ma250_pct']:.2f}% |"
        )

    lines.extend(
        [
            "",
            "### 当日最强的五只",
            "",
            "| 名称 | 涨跌幅 | 换手率 | 成交额 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )

    for _, row in tdx["strongest"].iterrows():
        lines.append(
            f"| {row['sec_name']} | {row['pct_change']:.2f}% | {row['turnover_pct']:.2f}% | {row['amount']:.0f} |"
        )

    lines.extend(
        [
            "",
            "## 初步结论",
            f"- 这版原型已经证明：`TDX MCP` 很适合承担白酒成分股和龙头快照，但 `Tushare` 这份本地缓存还不够长，暂时还不能对 `{SW_PROXY_NAME}` 做正式年线/收敛判断。",
            f"- 龙头层并非完全走弱，`站上60日均线` 的个股有 `{tdx['above_ma60_count']}` 只，但 `站上250日均线` 的只有 `{tdx['above_ma250_count']}` 只，说明白酒内部更像分化修复，而不是板块共振启动。",
            "- 因此这个混合原型当前最适合输出“观察中，等待补足板块历史数据后再做启动确认”。",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
