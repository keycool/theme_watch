import json
from pathlib import Path

from industry_start_strategy_v1_engine import evaluate_strategy, load_inputs


ROOT = Path(__file__).resolve().parent
SAMPLE_FILES = [
    ROOT / "strategy_input_white_liquor_sample.json",
    ROOT / "strategy_input_medical_sample.json",
    ROOT / "strategy_input_home_appliances_sample.json",
    ROOT / "strategy_input_semiconductor_sample.json",
]


def main() -> None:
    rows = []
    for path in SAMPLE_FILES:
        inputs = load_inputs(path)
        result = evaluate_strategy(inputs)
        rows.append(
            {
                "industry_name": result.industry_name,
                "industry_code": result.industry_code,
                "prefilter_label": result.prefilter_label,
                "final_label": result.final_label,
                "summary_line": result.summary_line,
            }
        )

    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
