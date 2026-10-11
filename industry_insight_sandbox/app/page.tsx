"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import bundledOverviewData from "../data/overview.json";
import StatusStrip from "./components/StatusStrip";


type OverviewData = typeof bundledOverviewData;
type Target = OverviewData["targets"][number] & {
  absorptionRankPct?: number | null;
  maStackCode?: string;
  maStateCode?: string;
  observation?: {
    position?: {
      ma60GapPct?: number | null;
      ma250GapPct?: number | null;
    };
  };
  route?: string;
};
type StageState = Target["stageStates"][number] & { warning?: boolean };

const LIVE_OVERVIEW_URL =
  "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json";

// 客观排序：按收盘价落在哪条均线之上，不再按方向性标签排序。
const MA_STATE_ORDER = [
  "above_ma250",
  "above_ma60",
  "above_ma20",
  "below_ma20_converged",
  "below_ma20",
];
const MA_STATE_TEXT: Record<string, string> = {
  above_ma250: "MA250 上方",
  above_ma60: "MA60 上方",
  above_ma20: "MA20 上方",
  below_ma20_converged: "MA20 下方",
  below_ma20: "MA20 下方",
};

function maStateRank(value: string | undefined) {
  const index = MA_STATE_ORDER.indexOf(value ?? "");
  return index === -1 ? MA_STATE_ORDER.length : index;
}

function maStateText(value: string | undefined) {
  return MA_STATE_TEXT[value ?? ""] ?? "待更新";
}

function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatDate(value: string) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function maStateClass(value: string | undefined) {
  if (value === "above_ma250") return "label-trend";
  if (value === "above_ma60") return "label-near";
  if (value === "above_ma20") return "label-watch";
  return "label-idle";
}

function TargetRow({ target }: { target: Target }) {
  return (
    <Link
      className="target-row"
      href={target.route || `/topic/${target.slug}`}
    >
      <div className="target-row-identity">
        <span className="target-kind">
          {target.kind === "index"
            ? "主题指数"
            : target.kind === "hk_qdii"
              ? "港股ETF"
              : "ETF"}
        </span>
        <strong>{target.name}</strong>
        <small className="mono">{target.code}</small>
      </div>
      <div className="target-row-index">
        <strong>{target.indexName}</strong>
        <small className="mono">{target.indexCode}</small>
      </div>
      <div className="target-row-status">
        <span className={`overview-label ${maStateClass(target.maStateCode)}`}>
          {maStateText(target.maStateCode)}
        </span>
        <span className="ma-lifecycle-label mono">
          {target.maStackCode ?? "均线待更新"}
        </span>
        <span className="rhythm-label">
          距MA60 {formatPercent(target.observation?.position?.ma60GapPct)}
          {" · "}距MA250{" "}
          {formatPercent(target.observation?.position?.ma250GapPct)}
        </span>
      </div>
      <div className="target-row-stages">
        {target.stageStates.map((rawStage, index) => {
          const stage = rawStage as StageState;
          const state = stage.passed
            ? "达到"
            : stage.warning
              ? "接近"
              : "未达";
          return (
            <span
              className={
                stage.passed
                  ? "stage-pass"
                  : stage.warning
                    ? "stage-warning"
                    : "stage-wait"
              }
              key={stage.title}
              title={`${stage.title}：${state}`}
            >
              <i />
              {index === 0 ? "位置" : index === 1 ? "均线" : "成分"}
            </span>
          );
        })}
        <small>{target.stagePassCount}/3</small>
      </div>
      <div className="target-row-metric">
        <span>距MA250</span>
        <strong className={(target.ma250Gap || 0) >= 0 ? "up" : "down"}>
          {formatPercent(target.ma250Gap)}
        </strong>
      </div>
      <div className="target-row-metric">
        <span>资金分位</span>
        <strong>
          {target.absorptionRankPct === null ||
          target.absorptionRankPct === undefined
            ? "—"
            : `${target.absorptionRankPct.toFixed(0)}%`}
        </strong>
      </div>
      <div className="target-row-metric">
        <span>当日</span>
        <strong className={(target.latestPct || 0) >= 0 ? "up" : "down"}>
          {formatPercent(target.latestPct, 2)}
        </strong>
      </div>
      <span className="target-row-arrow" aria-hidden="true">
        →
      </span>
    </Link>
  );
}

function DashboardHeader() {
  return (
    <div className="target-dashboard-head" aria-hidden="true">
      <span>标的</span>
      <span>判断指数</span>
      <span>均线位置 / 排列</span>
      <span>三层条件读数</span>
      <span>距MA250</span>
      <span>资金分位</span>
      <span>当日</span>
      <span />
    </div>
  );
}

function SignalSummary({
  total,
  confirmed,
  watching,
  latestDate,
}: {
  total: number;
  confirmed: number;
  watching: number;
  latestDate: string;
}) {
  return (
    <div className="overview-signal-summary">
      <div className="signal-summary-heading">
        <p className="eyebrow">MA GEOMETRY READOUT</p>
        <strong>今日均线位置读数</strong>
      </div>
      <div className="signal-summary-grid">
        <article>
          <span>全部标的</span>
          <strong>{total}</strong>
        </article>
        <article>
          <span>收盘在MA250上方</span>
          <strong className="confirmed-stat">{confirmed}</strong>
        </article>
        <article>
          <span>收盘在MA60上方</span>
          <strong>{watching}</strong>
        </article>
        <article>
          <span>数据日期</span>
          <strong className="date-stat">{formatDate(latestDate)}</strong>
        </article>
      </div>
    </div>
  );
}

export default function Home() {
  const [overviewData, setOverviewData] = useState<OverviewData>(
    bundledOverviewData,
  );
  const [label, setLabel] = useState("全部");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (["localhost", "127.0.0.1", "0.0.0.0"].includes(window.location.hostname)) {
      return;
    }
    let cancelled = false;
    fetch(`${LIVE_OVERVIEW_URL}?v=${Date.now()}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`Live overview HTTP ${response.status}`);
        return response.json() as Promise<OverviewData>;
      })
      .then((liveData) => {
        if (!cancelled && liveData.meta?.targetCount === 23) {
          setOverviewData(liveData);
        }
      })
      .catch(() => {
        // Keep the bundled snapshot when the live data branch is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const targets = overviewData.targets;
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return targets
      .filter(
        (target) =>
        (label === "全部" || maStateText(target.maStateCode) === label) &&
        (!normalized ||
          target.name.toLowerCase().includes(normalized) ||
          target.code.toLowerCase().includes(normalized) ||
          target.indexName.toLowerCase().includes(normalized)),
      )
      .sort(
        (left, right) =>
          maStateRank(left.maStateCode) - maStateRank(right.maStateCode) ||
          right.stagePassCount - left.stagePassCount ||
          (right.absorptionRankPct || 0) - (left.absorptionRankPct || 0) ||
          left.order - right.order,
      );
  }, [label, query, targets]);

  const aboveMa250Count = targets.filter(
    (target) => target.maStateCode === "above_ma250",
  ).length;
  const aboveMa60Count = targets.filter(
    (target) => target.maStateCode === "above_ma60",
  ).length;

  return (
    <main>
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            IW
          </span>
          <div>
            <strong>Industry Watch Lab</strong>
            <small>23 formal project targets</small>
          </div>
        </div>
        <StatusStrip
          generatedAt={overviewData.meta.generatedAt}
          latestDate={targets[0].latestDate}
        />
      </header>

      <section className="overview-hero shell">
        <div>
          <p className="eyebrow">PROJECT TARGET UNIVERSE / DIRECT CONSTITUENT VIEW</p>
          <h1>
            项目目标ETF与指数
            <br />
            <span>核心成分读数总览</span>
          </h1>
          <p>
            23个正式标的集中在同一张读数表中，按收盘价相对 MA20 / MA60 / MA250 的位置、
            成分股广度与成交额分位横向对照。点击任一标的进入成分股专题。
          </p>
        </div>
        <SignalSummary
          confirmed={aboveMa250Count}
          latestDate={targets[0].latestDate}
          total={overviewData.meta.targetCount}
          watching={aboveMa60Count}
        />
      </section>

      <section className="overview-dashboard shell">
        <div className="dashboard-title-row">
          <div>
            <p className="eyebrow">ALL TARGETS / THREE-STAGE WATCH</p>
            <h2>全部标的读数</h2>
            <p>默认按三层条件达到数排序，全部标的集中展示，不再按行业分块。</p>
          </div>
          <div className="overview-control-right">
            <select
              aria-label="按均线位置筛选"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            >
              <option>全部</option>
              {MA_STATE_ORDER.map((value) => (
                <option key={value}>{maStateText(value)}</option>
              ))}
            </select>
            <input
              aria-label="搜索ETF、指数或代码"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称 / 代码 / 跟踪指数"
              type="search"
              value={query}
            />
          </div>
        </div>
        <div className="target-dashboard">
          <DashboardHeader />
          {filtered.map((target) => (
            <TargetRow key={target.slug} target={target} />
          ))}
          {!filtered.length && (
            <div className="overview-empty">没有符合当前筛选条件的目标。</div>
          )}
        </div>
      </section>

      <footer className="footer shell">
        <div>
          <strong>范围说明</strong>
          <p>
            数据目标来自现有项目正式配置，不含人工通信对照组。生成时间{" "}
            {overviewData.meta.generatedAt}。
          </p>
        </div>
        <div className="footer-notes">
          <p>每个专题使用对应ETF的真实跟踪指数和最新权重；港股标的保留专用数据口径。</p>
          <p>核心成分优先覆盖60%指数权重，最多取20只，实际覆盖率逐页展示。</p>
          <p>申万二级不参与本沙盒专题标签，只保留为成分股行业文字参照。</p>
          <p>以上内容仅用于策略研究与方法验证，不构成投资建议。</p>
        </div>
      </footer>
    </main>
  );
}
