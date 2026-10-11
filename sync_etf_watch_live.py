#!/usr/bin/env python
"""Sync published ETF / industry-start watch data into a local mirror directory.

Production of this strategy runs on GitHub Actions (weekdays 21:05 / 22:30
Asia/Shanghai). It publishes the unified 25-target overview plus per-topic
payloads to the ``etf-watch-data`` branch, which the live site reads from
raw.githubusercontent.com.

This script is the missing local half: it pulls that published branch down,
validates it, backs up whatever was there before, and writes atomically.

It never runs the production calculator, never touches Tushare or Vercel, and
never commits, pushes or deploys.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

RAW_BASE = "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data"
DEFAULT_PROXY = "http://127.0.0.1:10809"

ROOT_FILES = (
    "overview.json",
    "all_topics.json",
)

# Published by the production workflow since commit 49bf3ae (2026-09-18). They stay
# "optional" only in the sense that a 404 does not fail the sync; arrival is now the
# expected state, so a non-empty absent list should be confirmed instead of assumed
# normal. Judge the state from optional_present/optional_absent, never from a note.
OPTIONAL_FILES = (
    "allocation_handoff.json",
    "signal_followup.json",
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_TARGET_DIR = REPO_ROOT / "live-data" / "etf-watch"
INPLACE_TARGET_DIR = REPO_ROOT / "industry_insight_sandbox" / "data"

EXPECTED_TARGET_COUNT = 25
EXPECTED_CORE_COUNT = 23
EXPECTED_HK_QDII_COUNT = 2

GENERATED_AT_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


class SyncError(RuntimeError):
    """Raised when the published payload cannot be trusted."""


def build_opener(proxy: str) -> urllib.request.OpenerDirector:
    proxy = (proxy or "").strip()
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    opener.addheaders = [("User-Agent", "etf-watch-local-sync")]
    return opener


def fetch_json(opener: urllib.request.OpenerDirector, url: str, timeout: int) -> Any:
    with opener.open(url, timeout=timeout) as response:  # type: ignore[attr-defined]
        return json.loads(response.read().decode("utf-8"))


def parse_generated_at(value: Any, label: str) -> datetime:
    raw = str(value or "").strip()
    for fmt in GENERATED_AT_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise SyncError(f"{label} generatedAt {raw!r} is not a recognised timestamp")


def topic_paths(overview: dict[str, Any]) -> list[str]:
    targets = overview.get("targets")
    if not isinstance(targets, list):
        raise SyncError("Published overview has no targets list")
    paths: list[str] = []
    seen: set[str] = set()
    for item in targets:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            raise SyncError("Published overview contains a target without a slug")
        if slug in seen:
            raise SyncError(f"Published overview contains duplicate slug {slug!r}")
        seen.add(slug)
        folder = "hk_qdii" if item.get("kind") == "hk_qdii" else "topics"
        paths.append(f"{folder}/{slug}.json")
    return paths


def validate_overview(overview: Any) -> dict[str, Any]:
    if not isinstance(overview, dict):
        raise SyncError("Published overview must be a JSON object")
    meta = overview.get("meta")
    if not isinstance(meta, dict):
        raise SyncError("Published overview has no meta object")
    targets = overview.get("targets")
    if not isinstance(targets, list):
        raise SyncError("Published overview has no targets list")

    counts = {
        "targetCount": (meta.get("targetCount"), EXPECTED_TARGET_COUNT),
        "coreTargetCount": (meta.get("coreTargetCount"), EXPECTED_CORE_COUNT),
        "hkQdiiCount": (meta.get("hkQdiiCount"), EXPECTED_HK_QDII_COUNT),
    }
    for key, (actual, expected) in counts.items():
        if actual is None:
            continue
        if int(actual) != expected:
            raise SyncError(f"overview meta {key}={actual}, expected {expected}")
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise SyncError(f"overview targets length {len(targets)}, expected {EXPECTED_TARGET_COUNT}")

    parse_generated_at(meta.get("generatedAt"), "overview")
    return overview


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def sync(
    target_dir: Path,
    *,
    proxy: str,
    timeout: int,
    include_topics: bool,
    allow_downgrade: bool,
    dry_run: bool,
) -> dict[str, Any]:
    opener = build_opener(proxy)

    overview_url = f"{RAW_BASE}/overview.json"
    overview = validate_overview(fetch_json(opener, overview_url, timeout))
    incoming_generated_at = parse_generated_at(
        overview["meta"].get("generatedAt"), "overview"
    )

    target_dir = target_dir.resolve()
    existing_overview_path = target_dir / "overview.json"
    existing_generated_at: datetime | None = None
    if existing_overview_path.exists():
        try:
            existing = json.loads(existing_overview_path.read_text(encoding="utf-8"))
            existing_generated_at = parse_generated_at(
                (existing.get("meta") or {}).get("generatedAt"), "existing overview"
            )
        except (json.JSONDecodeError, SyncError) as exc:
            raise SyncError(
                f"Existing {existing_overview_path} is unreadable, refusing to overwrite: {exc}"
            ) from exc

    if (
        existing_generated_at
        and incoming_generated_at < existing_generated_at
        and not allow_downgrade
    ):
        raise SyncError(
            "Refusing to downgrade overview.json: "
            f"{existing_generated_at:%Y-%m-%d %H:%M} -> {incoming_generated_at:%Y-%m-%d %H:%M}"
        )

    files: dict[str, bytes] = {}
    skipped: dict[str, str] = {}
    optional_present: list[str] = []
    optional_absent: list[str] = []

    overview_bytes = json.dumps(overview, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    files["overview.json"] = overview_bytes

    for name in (*ROOT_FILES[1:], *OPTIONAL_FILES):
        url = f"{RAW_BASE}/{name}"
        optional = name in OPTIONAL_FILES
        try:
            payload = fetch_json(opener, url, timeout)
        except urllib.error.HTTPError as exc:
            if optional and exc.code == 404:
                optional_absent.append(name)
            else:
                skipped[name] = f"{type(exc).__name__}: {exc}"
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            skipped[name] = f"{type(exc).__name__}: {exc}"
            continue
        files[name] = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if optional:
            optional_present.append(name)

    topic_count = 0
    if include_topics:
        for rel in topic_paths(overview):
            url = f"{RAW_BASE}/{rel}"
            try:
                payload = fetch_json(opener, url, timeout)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                skipped[rel] = f"{type(exc).__name__}: {exc}"
                continue
            files[rel] = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            topic_count += 1

    result: dict[str, Any] = {
        "source": RAW_BASE,
        "generated_at": overview["meta"].get("generatedAt"),
        "previous_generated_at": (
            existing_generated_at.strftime("%Y-%m-%d %H:%M") if existing_generated_at else None
        ),
        "target_count": len(overview["targets"]),
        "target_dir": str(target_dir),
        "files_written": sorted(files),
        "topic_files_written": topic_count,
        "optional_present": optional_present,
        "optional_absent": optional_absent,
        "optional_note": (
            "Both optional observation outputs arrived this run; they are published "
            "upstream, so absent is no longer the expected state."
            if len(optional_present) == len(OPTIONAL_FILES)
            else (
                "Some optional observation outputs arrived while others are absent; "
                "confirm upstream publication."
                if optional_present
                else "Optional observation outputs have been published upstream since "
                "2026-09-18 but none arrived this run; treat as a gap, not as expected absence."
            )
        ),
        "skipped": skipped,
        "dry_run": dry_run,
        "backup_dir": None,
        "status": "unchanged" if existing_generated_at == incoming_generated_at else "updated",
    }
    if dry_run:
        return result

    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    existing_files = [target_dir / rel for rel in files if (target_dir / rel).exists()]
    if existing_files:
        backup_dir = target_dir / "backups" / "etf-watch" / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        for path in existing_files:
            destination = backup_dir / path.relative_to(target_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        result["backup_dir"] = str(backup_dir)

    for rel, payload in files.items():
        write_bytes_atomic(target_dir / rel, payload)

    write_bytes_atomic(
        target_dir / "last_sync.json",
        json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync published ETF watch data from the etf-watch-data branch to a local mirror"
    )
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument(
        "--inplace",
        action="store_true",
        help=f"write into the repository data directory instead ({INPLACE_TARGET_DIR})",
    )
    parser.add_argument("--proxy", default=DEFAULT_PROXY, help="empty string disables the proxy")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--include-topics",
        action="store_true",
        help="also download topics/*.json and hk_qdii/*.json (25 extra files)",
    )
    parser.add_argument("--allow-downgrade", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_dir = INPLACE_TARGET_DIR if args.inplace else args.target_dir
    try:
        result = sync(
            target_dir,
            proxy=args.proxy,
            timeout=args.timeout_seconds,
            include_topics=args.include_topics,
            allow_downgrade=args.allow_downgrade,
            dry_run=args.dry_run,
        )
    except (SyncError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
