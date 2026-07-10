from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SUMMARY_DIR = ROOT / "logs" / "theme_watch_workflow"


def _latest_summary_path(summary_dir: Path) -> Path:
    candidates = sorted(summary_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No workflow summary JSON found in {summary_dir}")
    return candidates[0]


def _status_label(status: str) -> str:
    mapping = {
        "success": "成功",
        "warning": "告警",
        "failed": "失败",
        "skipped": "跳过",
    }
    return mapping.get(status, status)


def _build_text(payload: dict, pages_url: str, run_url: str) -> str:
    issues = payload.get("issues", [])
    issues_text = "无"
    if issues:
        issues_text = "\n".join(f"{idx + 1}. {issue}" for idx, issue in enumerate(issues[:5]))

    lines = [
        "行业主题观察每日更新",
        f"状态：{_status_label(str(payload.get('status', '')))}",
        f"交易日：{payload.get('end_date', '')}",
        f"运行 ID：{payload.get('run_id', '')}",
        f"是否交易日：{'是' if payload.get('is_trade_day') else '否'}",
        "问题清单：",
        issues_text,
    ]
    if pages_url:
        lines.append(f"报告链接：{pages_url}")
    if run_url:
        lines.append(f"运行日志：{run_url}")
    return "\n".join(lines)


def send_webhook(summary_dir: Path, webhook_url: str, pages_url: str, run_url: str) -> None:
    summary_path = _latest_summary_path(summary_dir)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    text = _build_text(payload, pages_url=pages_url, run_url=run_url)

    body = json.dumps(
        {
            "msg_type": "text",
            "content": {
                "text": text,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to send Feishu webhook: {exc}") from exc

    print("feishu_webhook_sent=1")
    print(f"feishu_webhook_response={response_body}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send theme watch summary to a Feishu webhook bot.")
    parser.add_argument("--summary-dir", default=str(DEFAULT_SUMMARY_DIR))
    parser.add_argument("--pages-url", default=os.getenv("THEME_WATCH_PAGES_URL", ""))
    parser.add_argument("--run-url", default=os.getenv("GITHUB_RUN_URL", ""))
    parser.add_argument("--webhook-url", default=os.getenv("FEISHU_WEBHOOK_URL", ""))
    args = parser.parse_args()

    if not args.webhook_url:
        print("feishu_webhook_skipped=missing_webhook_url")
        return

    send_webhook(
        summary_dir=Path(args.summary_dir),
        webhook_url=args.webhook_url,
        pages_url=args.pages_url,
        run_url=args.run_url,
    )


if __name__ == "__main__":
    main()
