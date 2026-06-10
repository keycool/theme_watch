from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
SCAN_PATH = ROOT / "sw_l1_strategy_scan.csv"
OUTPUT_MD = ROOT / "industry_strategy_leaderboard.md"


GROUP_ORDER = [
    "趋势延续型强势",
    "趋势延续型偏强",
    "接近启动",
    "启动确认",
    "观察中",
    "未启动",
]


def format_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def build_group_lines(df: pd.DataFrame, label: str) -> list[str]:
    group = df[df["final_label"] == label].copy()
    if group.empty:
        return [f"## {label}", "", "- （空）", ""]

    lines = [f"## {label}", ""]
    for _, row in group.iterrows():
        leader = row["leader_top1_name"] if pd.notna(row["leader_top1_name"]) else "-"
        leader_pct = format_pct(row["leader_top1_pct_change"])
        lines.append(
            f"- `{row['industry_name']}` `{row['industry_code']}`"
            f" | 龙头：`{leader}`"
            f" | 龙头涨跌：`{leader_pct}`"
            f" | 板块摘要：{row['summary_line']}"
        )
    lines.append("")
    return lines


def main() -> None:
    df = pd.read_csv(SCAN_PATH)
    df = df.sort_values(
        ["final_label", "prefilter_label", "total_mv_yi"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    lines = [
        "# 当前全行业分层榜单",
        "",
        "> 这套策略抓的是“刚要起来”的行业，不是“已经很强”的行业。",
        "> 因此，长趋势强行业应优先被归入“趋势延续对象”，而不是误判成“启动确认”。",
        "",
        "- 数据口径：申万一级行业，主样本池为总市值 `>= 5000亿`。",
        "- 当前版本已接入：板块结构、120日分位、250日年线、轻量龙头层、龙头趋势位置与持续性。",
        "- 当前版本仍未接入：更完整的龙头群体一致性、更多短期强弱排序字段。",
        "",
        "## 总览",
        "",
        f"- 总行业数：`{len(df)}`",
    ]

    for label in GROUP_ORDER:
        count = int((df["final_label"] == label).sum())
        lines.append(f"- `{label}`：`{count}`")

    lines.append("")

    for label in GROUP_ORDER:
        lines.extend(build_group_lines(df, label))

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote leaderboard to {OUTPUT_MD}")


if __name__ == "__main__":
    main()
