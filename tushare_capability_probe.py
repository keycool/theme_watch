import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

import tushare as ts


for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[proxy_var] = ""
    os.environ[proxy_var.lower()] = ""


OUTPUT_PATH = Path(__file__).with_name("tushare_capability_report.json")


def get_pro():
    token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN. Configure it in env or Tushare local config.")
    return ts.pro_api(token)


def classify_message(message: str) -> str:
    msg = (message or "").lower()
    if "频率超限" in message:
        return "rate_limited"
    if "无权限" in message or "权限" in message:
        return "permission_denied"
    if "proxyerror" in msg or "unable to connect to proxy" in msg:
        return "proxy_error"
    if "failed to establish a new connection" in msg or "connectionrefusederror" in msg:
        return "network_error"
    return "other_error"


def probe(name: str, fn: Callable[[], Any], expectation: str) -> Dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        result = fn()
        rows = None
        sample = None
        if hasattr(result, "empty"):
            rows = int(len(result))
            sample = result.head(3).to_dict(orient="records")
        return {
            "name": name,
            "expectation": expectation,
            "started_at": started_at,
            "status": "ok",
            "error_type": None,
            "message": None,
            "rows": rows,
            "sample": sample,
        }
    except Exception as exc:
        message = str(exc)
        return {
            "name": name,
            "expectation": expectation,
            "started_at": started_at,
            "status": "error",
            "error_type": classify_message(message),
            "message": message,
            "rows": None,
            "sample": None,
        }


def main():
    pro = get_pro()
    probes: List[Dict[str, Any]] = [
        probe(
            "trade_cal",
            lambda: pro.trade_cal(exchange="SSE", start_date="20260601", end_date="20260605"),
            "基础连通性与常规权限",
        ),
        probe(
            "stock_basic",
            lambda: pro.stock_basic(list_status="L", fields="ts_code,name,industry,list_date").head(5),
            "基础股票接口",
        ),
        probe(
            "daily_basic",
            lambda: pro.daily_basic(
                trade_date="20260527",
                fields="ts_code,trade_date,total_mv,circ_mv",
            ).head(5),
            "股票日度市值接口",
        ),
        probe(
            "limit_list_d",
            lambda: pro.limit_list_d(trade_date="20260527").head(5),
            "涨停/炸板接口",
        ),
        probe(
            "stk_limit",
            lambda: pro.stk_limit(ts_code="600519.SH", start_date="20260527", end_date="20260527"),
            "单股涨跌停价接口",
        ),
        probe(
            "index_classify",
            lambda: pro.index_classify(src="SW2021").head(5),
            "申万行业分类接口",
        ),
        probe(
            "index_member_all",
            lambda: pro.index_member_all(l1_code="801780.SI").head(5),
            "申万行业成分接口",
        ),
        probe(
            "sw_daily",
            lambda: pro.sw_daily(ts_code="801120.SI", start_date="20260520", end_date="20260602").head(5),
            "申万行业日线，正式版行业模型核心接口",
        ),
        probe(
            "ths_index",
            lambda: pro.ths_index(exchange="A", type="I").head(5),
            "同花顺行业板块列表接口",
        ),
        probe(
            "ths_daily",
            lambda: pro.ths_daily(ts_code="885530.TI", start_date="20250501", end_date="20250602").head(5),
            "同花顺行业日线，替代行业模型核心接口",
        ),
        probe(
            "ths_member",
            lambda: pro.ths_member(ts_code="885800.TI").head(5),
            "同花顺板块成分接口",
        ),
        probe(
            "daily",
            lambda: pro.daily(ts_code="600519.SH", start_date="20260520", end_date="20260602").head(5),
            "个股日线接口",
        ),
    ]

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_path": str(OUTPUT_PATH),
        "ok_count": sum(1 for item in probes if item["status"] == "ok"),
        "error_count": sum(1 for item in probes if item["status"] == "error"),
        "probes": probes,
    }

    OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
