from __future__ import annotations

from pathlib import Path

import pandas as pd

from theme_watch_config import PAGE_DIR, REPORT_DIR, ROOT, TOPIC_PAGES


INDEX_HTML = REPORT_DIR / "index.html"
SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _read_utf8(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    _require("\ufffd" not in text, f"{path} contains replacement characters.")
    return text


def _validate_index() -> None:
    _require(INDEX_HTML.exists(), f"Missing homepage: {INDEX_HTML}")
    html = _read_utf8(INDEX_HTML)
    _require('<meta charset="utf-8">' in html, "Homepage charset declaration is missing.")
    _require('<table class="overview-table">' in html, "Homepage overview table is missing.")
    _require('class="target-link"' in html, "Homepage target links are missing.")


def _validate_topic_pages() -> None:
    _require(PAGE_DIR.exists(), f"Missing topic page directory: {PAGE_DIR}")
    for page in TOPIC_PAGES:
        page_path = PAGE_DIR / page["output"]
        _require(page_path.exists(), f"Missing topic page: {page_path}")
        html = _read_utf8(page_path)

        _require("<article class=\"card\">" in html, f"{page['output']} has no card blocks.")
        _require("class=\"sparkline\"" in html, f"{page['output']} has no chart SVG.")
        _require(">数据不足<" not in html, f"{page['output']} has data-insufficient badge.")
        _require("历史数据不足" not in html, f"{page['output']} has empty chart text.")
        _require("暂时无法绘图" not in html, f"{page['output']} has empty chart text.")
        _require("暂无法画图" not in html, f"{page['output']} has empty chart text.")
        _require("metric-group primary" in html, f"{page['output']} missing primary metrics.")
        _require("metric-group auxiliary" in html, f"{page['output']} missing auxiliary metrics.")

        code_hits = [code for code in page["codes"] if code in html]
        _require(code_hits, f"{page['output']} missing expected industry codes.")


def _validate_scan_crowding() -> None:
    _require(SCAN_CSV.exists(), f"Missing scan CSV: {SCAN_CSV}")
    df = pd.read_csv(SCAN_CSV)
    _require("crowding_label" in df.columns, "Scan CSV missing crowding_label.")
    insufficient = df[df["crowding_label"].astype(str) == "数据不足"]
    _require(insufficient.empty, f"Scan CSV has data-insufficient crowding rows: {len(insufficient)}")


def main() -> None:
    _validate_index()
    _validate_topic_pages()
    _validate_scan_crowding()
    print(f"validated_homepage={INDEX_HTML}")
    print(f"validated_topic_pages={len(TOPIC_PAGES)}")


if __name__ == "__main__":
    main()
