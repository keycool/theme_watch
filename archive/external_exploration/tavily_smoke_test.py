import argparse
import json
import os
from pathlib import Path

from tavily import TavilyClient


for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[proxy_var] = ""
    os.environ[proxy_var.lower()] = ""


OUTPUT_PATH = Path(__file__).with_name("tavily_smoke_test_result.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Tavily search smoke test.")
    parser.add_argument(
        "--query",
        default="OpenAI latest API docs",
        help="Search query to run.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="Maximum number of search results to request.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = TavilyClient()
    result = client.search(args.query, max_results=args.max_results)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    items = result.get("results", [])
    print(f"query={args.query}")
    print(f"results={len(items)}")
    for item in items[: args.max_results]:
        print(f"- {item.get('title')} | {item.get('url')}")
    print(f"saved={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
