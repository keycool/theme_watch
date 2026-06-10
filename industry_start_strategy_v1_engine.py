import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent


def _bool_score(value: Optional[bool]) -> int:
    return 1 if value is True else 0


def _safe_ge(left: Optional[float], right: Optional[float]) -> Optional[bool]:
    if left is None or right is None:
        return None
    return left >= right


def _safe_gt(left: Optional[float], right: Optional[float]) -> Optional[bool]:
    if left is None or right is None:
        return None
    return left > right


@dataclass
class StrategyInputs:
    industry_code: str
    industry_name: str
    latest_close: Optional[float] = None
    ma250: Optional[float] = None
    ret_120d: Optional[float] = None
    ret_120d_rank_pct: Optional[float] = None
    close_to_120d_high_ratio: Optional[float] = None
    leaders_above_ma60_ratio: Optional[float] = None
    leaders_above_ma250_ratio: Optional[float] = None
    close_120d_high: Optional[float] = None
    close_120d_low: Optional[float] = None
    close_40d_low: Optional[float] = None
    range_first_80: Optional[float] = None
    range_last_40: Optional[float] = None
    amount_latest: Optional[float] = None
    amount_ma20: Optional[float] = None
    recent_2d_above_ma250: Optional[bool] = None
    leader_count: Optional[int] = None
    leader_top1_name: Optional[str] = None
    leader_top1_pct_change: Optional[float] = None
    leader_top1_above_ma60: Optional[bool] = None
    leader_top1_above_ma250: Optional[bool] = None
    leader_5d_rank_pct: Optional[float] = None
    leader_follow_ok: Optional[bool] = None
    leaders_above_ma60_count: Optional[int] = None
    leaders_above_ma250_count: Optional[int] = None
    local_activity_ok: Optional[bool] = None


@dataclass
class StrategyEvaluation:
    industry_code: str
    industry_name: str
    prefilter_label: str
    final_label: str
    trend_extension_strength: Optional[str]
    observation_strength: Optional[str]
    prefilter_hit_count: int
    structure_score: int
    a1_low_zone_ok: Optional[bool]
    a2_contraction_ok: Optional[bool]
    a3_no_new_low_ok: Optional[bool]
    a4_not_hot_ok: Optional[bool]
    structure_ok: bool
    b1_above_ma250_ok: Optional[bool]
    b2_volume_breakout_ok: Optional[bool]
    b3_hold_above_ma250_ok: Optional[bool]
    breakout_emerged: bool
    breakout_confirmed: bool
    c1_leaders_identified_ok: Optional[bool]
    c2_leader_outperform_ok: Optional[bool]
    c3_leader_follow_ok: Optional[bool]
    c4_leader_trend_ok: Optional[bool]
    leader_turning_strong_ok: bool
    leader_confirmed_ok: bool
    summary_line: str
    structure_comment: str
    breakout_comment: str
    leader_comment: str
    risk_comment: str


def compute_prefilter(inputs: StrategyInputs) -> tuple[str, int, Optional[str]]:
    p1_1 = _safe_gt(inputs.latest_close, None if inputs.ma250 is None else inputs.ma250 * 1.15)
    p1_2 = _safe_ge(inputs.ret_120d_rank_pct, 0.80)
    p1_3 = _safe_ge(inputs.close_to_120d_high_ratio, 0.95)
    p1_4 = None
    if inputs.leaders_above_ma60_ratio is not None and inputs.leaders_above_ma250_ratio is not None:
        p1_4 = inputs.leaders_above_ma60_ratio >= 0.67 and inputs.leaders_above_ma250_ratio >= 0.67

    hit_count = _bool_score(p1_1) + _bool_score(p1_2) + _bool_score(p1_3) + _bool_score(p1_4)
    if hit_count >= 2:
        strong = p1_1 is True and p1_2 is True and p1_4 is True
        return "趋势延续对象", hit_count, "趋势延续型强势" if strong else "趋势延续型偏强"
    return "启动识别对象", hit_count, None


def compute_structure(inputs: StrategyInputs) -> tuple[int, Optional[bool], Optional[bool], Optional[bool], Optional[bool], bool]:
    a1 = None
    if inputs.latest_close is not None and inputs.close_120d_high is not None:
        a1 = inputs.latest_close <= inputs.close_120d_high * 0.90

    a2 = None
    if inputs.range_first_80 not in (None, 0) and inputs.range_last_40 is not None:
        a2 = inputs.range_last_40 <= inputs.range_first_80 * 0.90

    a3 = None
    if inputs.close_40d_low is not None and inputs.close_120d_low is not None:
        a3 = inputs.close_40d_low >= inputs.close_120d_low * 1.02

    a4 = _safe_ge(0.50, inputs.ret_120d_rank_pct)

    score = _bool_score(a1) + _bool_score(a2) + _bool_score(a3) + _bool_score(a4)
    ok = all(value is True for value in (a1, a2, a3, a4))
    return score, a1, a2, a3, a4, ok


def compute_breakout(inputs: StrategyInputs) -> tuple[Optional[bool], Optional[bool], Optional[bool], bool, bool]:
    b1 = None
    if inputs.latest_close is not None and inputs.ma250 is not None and inputs.ma250 != 0:
        b1 = inputs.latest_close >= inputs.ma250 * 1.03

    b2 = None
    if inputs.amount_latest is not None and inputs.amount_ma20 not in (None, 0):
        b2 = inputs.amount_latest >= inputs.amount_ma20 * 1.20

    b3 = inputs.recent_2d_above_ma250

    emerged = b1 is True and b2 is True
    confirmed = emerged and b3 is True
    return b1, b2, b3, emerged, confirmed


def compute_leader(inputs: StrategyInputs) -> tuple[Optional[bool], Optional[bool], Optional[bool], Optional[bool], bool, bool]:
    c1 = None if inputs.leader_count is None else inputs.leader_count >= 1
    c2 = None
    if inputs.leader_top1_pct_change is not None or inputs.leader_5d_rank_pct is not None:
        c2 = bool(
            (inputs.leader_top1_pct_change is not None and inputs.leader_top1_pct_change >= 7)
            or (inputs.leader_5d_rank_pct is not None and inputs.leader_5d_rank_pct >= 0.80)
        )
    c3 = inputs.leader_follow_ok
    c4 = inputs.leader_top1_above_ma60

    turning_strong = c1 is True and c2 is True
    confirmed = turning_strong and c3 is True and c4 is True
    return c1, c2, c3, c4, turning_strong, confirmed


def compute_observation_strength(inputs: StrategyInputs, leader_turning_strong_ok: bool) -> Optional[str]:
    if inputs.local_activity_ok is not True and not leader_turning_strong_ok:
        return None

    ma60_ratio = inputs.leaders_above_ma60_ratio or 0.0
    ma250_ratio = inputs.leaders_above_ma250_ratio or 0.0

    if leader_turning_strong_ok or ma60_ratio >= 0.5 or ma250_ratio >= 0.5:
        return "偏强"
    return "偏弱"


def build_comments(
    prefilter_label: str,
    structure_ok: bool,
    breakout_emerged: bool,
    breakout_confirmed: bool,
    leader_turning_strong_ok: bool,
    leader_confirmed_ok: bool,
    local_activity_ok: Optional[bool],
    observation_strength: Optional[str],
    trend_extension_strength: Optional[str],
) -> tuple[str, str, str, str, str]:
    if prefilter_label == "趋势延续对象":
        summary = f"{trend_extension_strength}，不属于启动识别对象。"
        structure = "该行业已明显脱离低位整理阶段，结构层不再作为启动判断入口。"
        breakout = "该行业更适合按趋势延续理解，而不是按首次突破理解。"
        leader = "核心龙头整体趋势较强，说明它已进入趋势跟踪范畴。"
        risk = "当前标签不代表看空，仅代表不属于“刚启动”样本。"
        return summary, structure, breakout, leader, risk

    if structure_ok and breakout_confirmed and leader_confirmed_ok:
        summary = "启动确认，板块与龙头条件同时闭合。"
    elif structure_ok and breakout_emerged and leader_turning_strong_ok:
        summary = "接近启动，板块和龙头已共振，但确认条件未完全闭合。"
    elif leader_turning_strong_ok or structure_ok or breakout_emerged or local_activity_ok is True:
        if observation_strength:
            summary = f"观察中（{observation_strength}），已有局部转强线索，但条件不完整。"
        else:
            summary = "观察中，已有局部转强线索，但条件不完整。"
    else:
        summary = "未启动，板块和龙头均未形成有效启动信号。"

    structure = "结构成立。" if structure_ok else "结构层尚未完全成立或数据不足。"
    if breakout_confirmed:
        breakout = "板块突破已确认。"
    elif breakout_emerged:
        breakout = "板块出现突破迹象，但尚未确认。"
    else:
        breakout = "板块尚未出现有效突破。"

    if leader_confirmed_ok:
        leader = "龙头确认成立。"
    elif leader_turning_strong_ok:
        leader = "龙头已有转强迹象，但持续性或趋势位置未完全确认。"
    else:
        leader = "龙头层尚未形成明确带动。"

    risk = "若板块历史样本不足，结构层和突破层判断应视为占位结果。"
    return summary, structure, breakout, leader, risk


def evaluate_strategy(inputs: StrategyInputs) -> StrategyEvaluation:
    prefilter_label, hit_count, trend_extension_strength = compute_prefilter(inputs)
    structure_score, a1, a2, a3, a4, structure_ok = compute_structure(inputs)
    b1, b2, b3, breakout_emerged, breakout_confirmed = compute_breakout(inputs)
    c1, c2, c3, c4, leader_turning_strong_ok, leader_confirmed_ok = compute_leader(inputs)
    observation_strength = compute_observation_strength(inputs, leader_turning_strong_ok)

    if prefilter_label == "趋势延续对象":
        final_label = trend_extension_strength or "趋势延续型偏强"
    elif structure_ok and breakout_confirmed and leader_confirmed_ok:
        final_label = "启动确认"
    elif structure_ok and breakout_emerged and leader_turning_strong_ok:
        final_label = "接近启动"
    elif structure_ok or breakout_emerged or leader_turning_strong_ok or inputs.local_activity_ok is True:
        final_label = "观察中"
    else:
        final_label = "未启动"

    summary, structure_comment, breakout_comment, leader_comment, risk_comment = build_comments(
        prefilter_label=prefilter_label,
        structure_ok=structure_ok,
        breakout_emerged=breakout_emerged,
        breakout_confirmed=breakout_confirmed,
        leader_turning_strong_ok=leader_turning_strong_ok,
        leader_confirmed_ok=leader_confirmed_ok,
        local_activity_ok=inputs.local_activity_ok,
        observation_strength=observation_strength,
        trend_extension_strength=trend_extension_strength,
    )

    return StrategyEvaluation(
        industry_code=inputs.industry_code,
        industry_name=inputs.industry_name,
        prefilter_label=prefilter_label,
        final_label=final_label,
        trend_extension_strength=trend_extension_strength,
        observation_strength=observation_strength,
        prefilter_hit_count=hit_count,
        structure_score=structure_score,
        a1_low_zone_ok=a1,
        a2_contraction_ok=a2,
        a3_no_new_low_ok=a3,
        a4_not_hot_ok=a4,
        structure_ok=structure_ok,
        b1_above_ma250_ok=b1,
        b2_volume_breakout_ok=b2,
        b3_hold_above_ma250_ok=b3,
        breakout_emerged=breakout_emerged,
        breakout_confirmed=breakout_confirmed,
        c1_leaders_identified_ok=c1,
        c2_leader_outperform_ok=c2,
        c3_leader_follow_ok=c3,
        c4_leader_trend_ok=c4,
        leader_turning_strong_ok=leader_turning_strong_ok,
        leader_confirmed_ok=leader_confirmed_ok,
        summary_line=summary,
        structure_comment=structure_comment,
        breakout_comment=breakout_comment,
        leader_comment=leader_comment,
        risk_comment=risk_comment,
    )


def load_inputs(path: Path) -> StrategyInputs:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StrategyInputs(**payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="行业启动策略 V1 规则引擎")
    parser.add_argument("--input", type=Path, required=True, help="JSON 输入文件路径")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 结果")
    args = parser.parse_args()

    inputs = load_inputs(args.input)
    evaluation = evaluate_strategy(inputs)

    if args.json:
        print(json.dumps(asdict(evaluation), ensure_ascii=False, indent=2))
        return

    print(f"{evaluation.industry_name}({evaluation.industry_code})")
    print(f"前置分流: {evaluation.prefilter_label}")
    print(f"最终标签: {evaluation.final_label}")
    print(f"摘要: {evaluation.summary_line}")
    print(f"结构: {evaluation.structure_comment}")
    print(f"突破: {evaluation.breakout_comment}")
    print(f"龙头: {evaluation.leader_comment}")
    print(f"风险: {evaluation.risk_comment}")


if __name__ == "__main__":
    main()
