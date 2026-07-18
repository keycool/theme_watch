"use client";

import { useEffect, useMemo, useState } from "react";
import bundledOverviewData from "../data/overview.json";


type OverviewData = typeof bundledOverviewData;
type Target = OverviewData["targets"][number];

const LIVE_OVERVIEW_URL =
  "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json";

const LABEL_ORDER = ["启动确认", "接近启动", "观察中", "未启动", "趋势延续"];

function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatDate(value: string) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function labelClass(label: string) {
  if (label === "启动确认") return "label-confirmed";
  if (label === "接近启动") return "label-near";
  if (label === "观察中") return "label-watch";
  if (label === "趋势延续") return "label-trend";
  return "label-idle";
}

function TargetRow({ target }: { target: Target }) {
  return (
    <a className="target-row" href={`/topic/${target.slug}`}>
      <div className="target-row-identity">
        <span className="target-kind">
          {target.kind === "etf" ? "ETF" : "主题指数"}
        </span>
        <strong>{target.name}</strong>
        <small className="mono">{target.code}</small>
      </div>
      <div className="target-row-index">
        <strong>{target.indexName}</strong>
        <small className="mono">{target.indexCode}</small>
      </div>
      <div>
        <span className={`overview-label ${labelClass(target.label)}`}>
          {target.label}
        </span>
      </div>
      <div className="target-row-stages">
        {target.stageStates.map((stage, index) => (
          <span
            className={stage.passed ? "stage-pass" : "stage-wait"}
            key={stage.title}
            title={`${stage.title}：${stage.passed ? "通过" : "未通过"}`}
          >
            <i />
            {index === 0 ? "低位" : index === 1 ? "突破" : "龙头"}
          </span>
        ))}
        <small>{target.stagePassCount}/3</small>
      </div>
      <div className="target-row-metric">
        <span>距MA250</span>
        <strong className={(target.ma250Gap || 0) >= 0 ? "up" : "down"}>
          {formatPercent(target.ma250Gap)}
        </strong>
      </div>
      <div className="target-row-metric">
        <span>核心成交</span>
        <strong>{target.amountRatio20?.toFixed(2) || "—"}×</strong>
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
    </a>
  );
}

function DashboardHeader() {
  return (
    <div className="target-dashboard-head" aria-hidden="true">
      <span>标的</span>
      <span>判断指数</span>
      <span>启动状态</span>
      <span>三层启动条件</span>
      <span>距MA250</span>
      <span>核心成交</span>
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
        <p className="eyebrow">TODAY&apos;S STARTUP WATCH</p>
        <strong>今日启动观察</strong>
      </div>
      <div className="signal-summary-grid">
        <article>
          <span>全部标的</span>
          <strong>{total}</strong>
        </article>
        <article>
          <span>启动确认</span>
          <strong className="confirmed-stat">{confirmed}</strong>
        </article>
        <article>
          <span>启动观察</span>
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
    let cancelled = false;
    fetch(`${LIVE_OVERVIEW_URL}?v=${Date.now()}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`Live overview HTTP ${response.status}`);
        return response.json() as Promise<OverviewData>;
      })
      .then((liveData) => {
        if (!cancelled && liveData.meta?.targetCount === 20) {
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
        (label === "全部" || target.label === label) &&
        (!normalized ||
          target.name.toLowerCase().includes(normalized) ||
          target.code.toLowerCase().includes(normalized) ||
          target.indexName.toLowerCase().includes(normalized)),
      )
      .sort(
        (left, right) =>
          right.stagePassCount - left.stagePassCount ||
          (right.amountRatio20 || 0) - (left.amountRatio20 || 0) ||
          left.order - right.order,
      );
  }, [label, query, targets]);

  const confirmedCount = targets.filter(
    (target) => target.label === "启动确认",
  ).length;
  const watchCount = targets.filter((target) =>
    ["接近启动", "观察中"].includes(target.label),
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
            <small>20 formal project targets</small>
          </div>
        </div>
        <div className="sandbox-badge">
          <span />
          封闭沙盒 · 不接入生产
        </div>
      </header>

      <section className="overview-hero shell">
        <div>
          <p className="eyebrow">PROJECT TARGET UNIVERSE / DIRECT CONSTITUENT VIEW</p>
          <h1>
            项目目标ETF与指数
            <br />
            <span>核心成分观察总览</span>
          </h1>
          <p>
            20个正式标的集中在同一张启动观察表中，直接对照低位收敛、带量突破年线与
            权重龙头确认。点击任一标的进入成分股专题。
          </p>
        </div>
        <SignalSummary
          confirmed={confirmedCount}
          latestDate={targets[0].latestDate}
          total={overviewData.meta.targetCount}
          watching={watchCount}
        />
      </section>

      <section className="overview-dashboard shell">
        <div className="dashboard-title-row">
          <div>
            <p className="eyebrow">ALL TARGETS / THREE-STAGE WATCH</p>
            <h2>全部标的启动观察</h2>
            <p>默认按三层条件通过数排序，全部标的集中展示，不再按行业分块。</p>
          </div>
          <div className="overview-control-right">
            <select
              aria-label="按启动状态筛选"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            >
              <option>全部</option>
              {LABEL_ORDER.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
            <input
              aria-label="搜索ETF、指数或代码"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称 / 代码 / 判断指数"
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
          <p>每个专题独立使用对应ETF的真实跟踪指数和最新月度权重。</p>
          <p>核心成分优先覆盖60%指数权重，最多取20只，实际覆盖率逐页展示。</p>
          <p>申万二级不参与本沙盒专题标签，只保留为成分股行业文字参照。</p>
          <p>以上内容仅用于策略研究与观察，不构成投资建议。</p>
        </div>
      </footer>
    </main>
  );
}
