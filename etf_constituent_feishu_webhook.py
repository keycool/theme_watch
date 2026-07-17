from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_SUMMARY_DIR = ROOT / "logs" / "etf_constituent_workflow"
DEFAULT_OVERVIEW_PATH = (
    ROOT / "industry_insight_sandbox" / "data" / "overview.json"
)
DEFAULT_KEYWORD = "theme_watch"


def _latest_summary_path(summary_dir: Path) -> Path | None:
    candidates = sorted(
        summary_dir.rglob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _status_label(status: str) -> str:
    return {
        "success": "成功",
        "warning": "告警",
        "failed": "失败",
        "failure": "失败",
        "cancelled": "取消",
        "skipped": "跳过",
    }.get(status, status or "未知")


def _format_labels(labels: dict[str, Any]) -> str:
    preferred = ["趋势延续", "观察中", "未启动", "启动确认"]
    ordered = [
        f"{label} {labels[label]}"
        for label in preferred
        if label in labels
    ]
    ordered.extend(
        f"{label} {count}"
        for label, count in labels.items()
        if label not in preferred
    )
    return "｜".join(ordered) if ordered else "无"


def _format_named_targets(overview: dict[str, Any], label: str) -> str:
    targets = [
        f"{item.get('name', '')}({item.get('code', '')})"
        for item in overview.get("targets", [])
        if item.get("label") == label
    ]
    return "、".join(targets) if targets else "无"


def _build_text(
    summary: dict[str, Any],
    overview: dict[str, Any],
    *,
    run_url: str,
    site_url: str,
    keyword: str,
    job_status: str,
) -> str:
    summary_status = str(summary.get("status", ""))
    effective_status = (
        job_status
        if job_status and job_status not in {"success", "skipped"}
        else summary_status or job_status
    )
    overview_targets = overview.get("targets", [])
    derived_metrics = {
        "target_count": len(overview_targets),
        "etf_count": sum(item.get("kind") == "etf" for item in overview_targets),
        "index_count": sum(
            item.get("kind") == "index" for item in overview_targets
        ),
        "latest_date": next(
            (
                item.get("latestDate")
                for item in overview_targets
                if item.get("latestDate")
            ),
            "",
        ),
        "weight_dates": sorted(
            {
                item.get("weightDate")
                for item in overview_targets
                if item.get("weightDate")
            }
        ),
        "labels": dict(
            Counter(
                item.get("label", "未知")
                for item in overview_targets
            )
        ),
    }
    metrics = {**derived_metrics, **summary.get("metrics", {})}
    labels = metrics.get("labels", {})
    issues = summary.get("issues", [])
    issues_text = "无" if not issues else "；".join(str(item) for item in issues[:5])
    weight_dates = metrics.get("weight_dates", [])
    weight_text = "、".join(str(item) for item in weight_dates) or "-"

    lines = [
        keyword,
        "ETF 核心成分启动观察",
        f"状态：{_status_label(effective_status)}",
        f"交易日：{summary.get('end_date', metrics.get('latest_date', '-'))}",
        (
            "观察对象："
            f"{metrics.get('target_count', 0)} 个"
            f"（ETF {metrics.get('etf_count', 0)}｜指数 {metrics.get('index_count', 0)}）"
        ),
        f"标签分布：{_format_labels(labels)}",
        f"趋势延续：{_format_named_targets(overview, '趋势延续')}",
        f"观察中：{_format_named_targets(overview, '观察中')}",
        f"指数权重日：{weight_text}",
        f"问题：{issues_text}",
    ]
    if site_url:
        lines.append(f"观察网页：{site_url}")
    if run_url:
        lines.append(f"运行详情：{run_url}")
    return "\n".join(lines)


def _build_sign(secret: str) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return timestamp, base64.b64encode(digest).decode("utf-8")


def _send_message(webhook_url: str, secret: str, text: str) -> dict[str, Any]:
    message: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        timestamp, sign = _build_sign(secret)
        message["timestamp"] = timestamp
        message["sign"] = sign

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to send ETF constituent webhook: {exc}") from exc

    try:
        response_payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Webhook returned a non-JSON response: {response_text}"
        ) from exc

    error_code = response_payload.get(
        "code",
        response_payload.get(
            "StatusCode",
            response_payload.get("status_code", 0),
        ),
    )
    if error_code not in (0, "0", None):
        raise RuntimeError(f"Webhook rejected the message: {response_text}")
    return response_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send ETF constituent workflow summary to Feishu."
    )
    parser.add_argument("--summary-dir", default=str(DEFAULT_SUMMARY_DIR))
    parser.add_argument("--overview-path", default=str(DEFAULT_OVERVIEW_PATH))
    parser.add_argument("--run-url", default=os.getenv("GITHUB_RUN_URL", ""))
    parser.add_argument("--site-url", default=os.getenv("ETF_WATCH_SITE_URL", ""))
    parser.add_argument("--job-status", default=os.getenv("WORKFLOW_JOB_STATUS", ""))
    parser.add_argument("--webhook-url", default=os.getenv("FEISHU_WEBHOOK_URL", ""))
    parser.add_argument(
        "--webhook-secret",
        default=os.getenv("FEISHU_WEBHOOK_SECRET", ""),
    )
    parser.add_argument(
        "--keyword",
        default=os.getenv("FEISHU_WEBHOOK_KEYWORD", DEFAULT_KEYWORD),
    )
    parser.add_argument("--require-webhook", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary_dir = Path(args.summary_dir)
    summary = _read_json(_latest_summary_path(summary_dir))
    overview = _read_json(Path(args.overview_path))
    text = _build_text(
        summary,
        overview,
        run_url=args.run_url,
        site_url=args.site_url,
        keyword=args.keyword,
        job_status=args.job_status,
    )

    if args.dry_run:
        print(text)
        return

    if not args.webhook_url:
        if args.require_webhook:
            raise RuntimeError("FEISHU_WEBHOOK_URL is not configured.")
        print("feishu_webhook_skipped=missing_webhook_url")
        return

    response = _send_message(args.webhook_url, args.webhook_secret, text)
    print("feishu_webhook_sent=1")
    print(
        "feishu_webhook_response="
        + json.dumps(response, ensure_ascii=False, sort_keys=True)
    )


if __name__ == "__main__":
    main()
