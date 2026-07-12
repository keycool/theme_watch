from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
from pathlib import Path


def _latest_summary_path(summary_dir: Path) -> Path:
    candidates = sorted(summary_dir.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No workflow summary JSON found in {summary_dir}")
    return candidates[0]


def _sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_text(summary: dict[str, object], keyword: str, pages_url: str, run_url: str) -> str:
    run_id = str(summary.get("run_id", "-"))
    status = str(summary.get("status", "-"))
    end_date = str(summary.get("end_date", "-"))
    issues = [str(item) for item in summary.get("issues", [])]
    issues_text = "\n".join(f"- {item}" for item in issues[:8]) if issues else "- 无"
    return (
        f"{keyword}\n"
        f"theme_watch 工作流结果\n"
        f"run_id: {run_id}\n"
        f"status: {status}\n"
        f"end_date: {end_date}\n"
        f"issues_count: {len(issues)}\n"
        f"issues:\n{issues_text}\n"
        f"pages: {pages_url}\n"
        f"github_actions: {run_url}"
    )


def send_webhook(summary_dir: Path, webhook_url: str, webhook_secret: str, keyword: str, pages_url: str, run_url: str) -> None:
    summary_path = _latest_summary_path(summary_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    timestamp = str(int(time.time()))
    payload = {
        "timestamp": timestamp,
        "sign": _sign(webhook_secret, timestamp) if webhook_secret else "",
        "msg_type": "text",
        "content": {
            "text": _build_text(summary, keyword, pages_url, run_url),
        },
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
    print("feishu_webhook_sent=1")
    print(f"feishu_webhook_response={body}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send theme watch workflow summary to Feishu webhook.")
    parser.add_argument("--summary-dir", default="logs/theme_watch_workflow")
    args = parser.parse_args()

    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    webhook_secret = os.environ.get("FEISHU_WEBHOOK_SECRET", "").strip()
    keyword = os.environ.get("FEISHU_WEBHOOK_KEYWORD", "theme_watch").strip() or "theme_watch"
    pages_url = os.environ.get("THEME_WATCH_PAGES_URL", "").strip()
    run_url = os.environ.get("GITHUB_RUN_URL", "").strip()

    if not webhook_url:
        print("feishu_webhook_skipped=missing_url")
        return

    send_webhook(
        summary_dir=Path(args.summary_dir),
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        keyword=keyword,
        pages_url=pages_url,
        run_url=run_url,
    )


if __name__ == "__main__":
    main()
