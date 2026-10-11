# market_context 接入说明（给 GPT）

> 目标：把「全市场一起跌 vs 单独被砸」的横截面读数接进 `run_etf_constituent_workflow.py`。
> 当前已接入 `run_etf_constituent_workflow.py`：在统一合并、allocation handoff、signal follow-up 之后运行，
> 并随 `etf-watch-data` 一起发布。以下内容作为接口和硬约束记录。

---

## 1. 这个东西是什么

模块：`D:\CC\Industry Insight\industry_insight_sandbox\build_market_context.py`

它读全部 25 个标的（A 股 24 + 港股通/QDII）的最近 5 日收益，算**横截面中位数**，
再给每个标的打一个 `declineRegime`：

| 条件 | regime | 含义 |
| --- | --- | --- |
| 本标的 ret5 > −3% | `none` | 没急跌 |
| 本标的 ret5 ≤ −3% 且横截面中位数 ≤ −3% | `market_wide` | 全市场一起跌 |
| 本标的 ret5 ≤ −3% 但横截面没跌 | `single_name` | 单独被砸 |

来源：2026-09-18 急跌历史验证里**唯一显著**的结论（全市场一起跌 − 单独被砸 = +1.50% 20 日超额）。
该验证已归档为历史资料，**不作为决策依据**。

**纯观察读数，不含任何买卖含义。** 不要给它加 action / 不加信号判定。

---

## 2. 接口（两种接法，选一种即可）

### 接法 A：子进程（生产编排采用，跟现有脚本风格一致）

```python
from pathlib import Path
MARKET_CONTEXT_BUILDER = SANDBOX_DIR / "build_market_context.py"
```

`_run_generators()` 的 `commands` 列表中，放在 `SIGNAL_FOLLOWUP_BUILDER` **之后**：

```python
    commands = [
        [sys.executable, str(GENERATOR), "--end-date", end_date],
        *[
            [sys.executable, str(generator), "--end-date", end_date]
            for generator in HK_GENERATORS
        ],
        [sys.executable, str(OVERVIEW_MERGER)],
        [sys.executable, str(ALLOCATION_HANDOFF_BUILDER)],
        [sys.executable, str(SIGNAL_FOLLOWUP_BUILDER)],
        [sys.executable, str(MARKET_CONTEXT_BUILDER)],   # ← 新增这一行
    ]
```

脚本自己会打印一行摘要，可直接进 log：

```
market_context asOf=20260813 median=0.2811 regimes={'none': 24, 'single_name': 1} backfilled=0
```

### 接法 B：库调用

```python
import sys
sys.path.insert(0, str(SANDBOX_DIR))
from build_market_context import build_and_backfill

payload = build_and_backfill()          # 用默认路径
# 或：build_and_backfill(overview_path=..., output_path=...)
payload["meta"]["asOf"]                 # '20260813'
payload["meta"]["marketRet5MedianPct"]  # 0.2811
payload["regimeCounts"]                 # {'none': 24, 'single_name': 1}
payload["backfillCount"]                # 本次发生变化的写回处数
```

---

## 3. 硬约束（改的时候别踩）

1. **顺序不能动**：必须在 `generate` → `merge_hk_qdii_overview` 之后跑。
   它依赖 `data/overview.json` 里已有全部 25 个标的，且 `latestDate` 唯一；
   不满足会 `RuntimeError: Overview latestDate is not unique`。
2. **幂等**：`attach()` 先比对再写，重复跑 `backfilled=0`，不会污染产物。
3. **输入**：`data/all_topics.json`、`hk_qdii_targets.json`、各 `data/topics/*.json`、各港股数据文件。
   **输出**：`data/market_context.json` + 就地回填 `summary.observation.context`（单标的与 overview 都回写）。
4. **不要动** `SCHEMA_VERSION`（当前 `1.0`）、`DECLINE_THRESHOLD_PCT`（`−3.0`）、`RET5_WINDOW`（`5`）。
   这三个是验证口径本身，改了就跟历史验证对不上。
5. **`declineRegime` 只有三个取值**，前端 `MovingAverageLifecycle.tsx` 里类型是 `string`（不是字面量联合），
   因为 JSON inline import 会推断成 `string`。
6. **历史补不出来**：存量 JSON 没有历史横截面，只能从首次运行日起逐日积累。
   所以每个 context 都带 `contextAsOf`，别让它被当成「历史上一直有」。

---

## 4. 改完怎么验

```bash
cd "D:/CC/Industry Insight/industry_insight_sandbox"

# 1) Python 全量测试（应 75 passed）
python -m unittest discover -s tests -p "test_*.py"

# 2) 类型检查（只应有 db/index.ts、worker/index.ts 的既有 cloudflare 报错）
cd ../ && npx tsc --noEmit && npm run build

# 3) 渲染测试（应 11 pass / 0 fail）
node --test industry_insight_sandbox/tests/rendered-html.test.mjs

# 4) 幂等自检：连跑两次 build_market_context.py，第二次 backfilled 必须是 0
python build_market_context.py
python build_market_context.py
```

---

## 5. 已完成的周边（不用重复做）

- `data/market_context.json` 已生成（`schemaVersion 1.0`，asOf 20260813）。
- 前端 `MovingAverageLifecycle.tsx` 的 `ObservationBlock` 已支持 `context` 字段。
- `tests/test_market_context.py` 已有 10 条测试覆盖 `ret5_pct` / `classify` 边界 / 横截面 / 产物契约。
- 两份 SOP 已写入 `market_context_builder` 与 `output_schema.market_context` 章节，
  `market_context.json` 已在发布文件清单里。
- 数据快照备份：`.backup/20260921/data_before_market_context/`。
