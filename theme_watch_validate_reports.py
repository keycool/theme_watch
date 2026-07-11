from __future__ import annotations

from pathlib import Path

from theme_watch_config import PAGE_DIR, REPORT_DIR, TOPIC_PAGES


INDEX_HTML = REPORT_DIR / "index.html"


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

    for page in TOPIC_PAGES:
        href = f"pages/{page['output']}"
        _require(href in html, f"Homepage missing topic link: {href}")


def _validate_topic_pages() -> None:
    _require(PAGE_DIR.exists(), f"Missing topic page directory: {PAGE_DIR}")
    for page in TOPIC_PAGES:
        page_path = PAGE_DIR / page["output"]
        _require(page_path.exists(), f"Missing topic page: {page_path}")
        html = _read_utf8(page_path)

        _require("<article class=\"card\">" in html, f"{page['output']} has no card blocks.")
        _require("class=\"sparkline\"" in html, f"{page['output']} has no chart SVG.")
        _require("metric-group primary" in html, f"{page['output']} missing primary metrics.")
        _require("metric-group auxiliary" in html, f"{page['output']} missing auxiliary metrics.")

        code_hits = [code for code in page["codes"] if code in html]
        _require(code_hits, f"{page['output']} missing expected industry codes.")


def main() -> None:
    _validate_index()
    _validate_topic_pages()
    print(f"validated_homepage={INDEX_HTML}")
    print(f"validated_topic_pages={len(TOPIC_PAGES)}")


if __name__ == "__main__":
    main()
