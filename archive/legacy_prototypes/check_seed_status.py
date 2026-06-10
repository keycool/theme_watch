from pathlib import Path


BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "wait_and_seed_sw_cache.log"
RESULT_PATH = BASE_DIR / "industry_start_scan_result.csv"
SUMMARY_PATH = BASE_DIR / "industry_start_scan_summary.txt"


def tail_lines(path: Path, max_lines: int = 10) -> str:
    if not path.exists():
        return "(missing)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "(empty)"
    return "\n".join(lines[-max_lines:])


def file_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"exists ({stat.st_size} bytes)"


def main():
    print("Seed Cache Status")
    print(f"log: {file_status(LOG_PATH)}")
    print(f"result_csv: {file_status(RESULT_PATH)}")
    print(f"summary_txt: {file_status(SUMMARY_PATH)}")
    print()
    print("Last log lines:")
    print(tail_lines(LOG_PATH, max_lines=12))
    print()
    print("Current summary:")
    print(tail_lines(SUMMARY_PATH, max_lines=20))


if __name__ == "__main__":
    main()
