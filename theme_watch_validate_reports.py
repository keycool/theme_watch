from __future__ import annotations

from pathlib import Path

from theme_watch_config import PAGE_DIR, TOPIC_PAGES


ROOT = Path(__file__).resolve().parent
INDEX_HTML = ROOT / "reports" / "theme_watch" / "index.html"


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def _require_no_empty_chart(html: str, page_name: str) -> None:
    empty_markers = [
        "历史数据不足",
        "暂时无法绘图",
        "暂无法画图",
    ]
    for marker in empty_markers:
        _require(marker not in html, f"Topic page has empty chart marker {marker}: {page_name}")


def _validate_index() -> None:
    _require(INDEX_HTML.exists(), "Homepage missing: reports/theme_watch/index.html")
    html = INDEX_HTML.read_text(encoding="utf-8", errors="replace")
    _require("<meta charset=\"utf-8\">" in html, "Homepage missing utf-8 charset.")
    _require("<table class=\"overview-table\">" in html, "Homepage missing overview table.")
    _require("class=\"target-link\"" in html, "Homepage missing topic links.")
    _require("\ufffd" not in html, "Homepage contains replacement characters.")
    print(f"validated_homepage={INDEX_HTML}")


def _validate_topic_pages() -> None:
    validated = 0
    for page in TOPIC_PAGES:
        path = PAGE_DIR / page["output"]
        _require(path.exists(), f"Topic page missing: {path.name}")
        html = path.read_text(encoding="utf-8", errors="replace")
        _require("<article class=\"card\">" in html, f"Topic page missing cards: {path.name}")
        _require("class=\"sparkline\"" in html, f"Topic page missing sparkline: {path.name}")
        _require_no_empty_chart(html, path.name)
        _require("主指标" in html, f"Topic page missing primary metrics: {path.name}")
        _require("辅助指标" in html, f"Topic page missing auxiliary metrics: {path.name}")
        _require(any(code in html for code in page["codes"]), f"Topic page missing expected SW code: {path.name}")
        _require("\ufffd" not in html, f"Topic page contains replacement characters: {path.name}")
        validated += 1
    print(f"validated_topic_pages={validated}")


def main() -> None:
    _validate_index()
    _validate_topic_pages()
    print("theme_watch_validate_reports_ok=1")


if __name__ == "__main__":
    main()
